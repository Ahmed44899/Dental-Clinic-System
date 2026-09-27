from clinics.api import clinic_for
from clinics.querysets import membership_prefetch
from .filters import AppointmentFilter

from rest_framework import generics, permissions
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Prefetch
from rest_framework.exceptions import ValidationError
from accounts.models import CustomUser
from accounts.permissions import (
    AppointmentAccessPermission,
    InvoiceAccessPermission,
    is_clinic_admin,
    is_dentist,
    is_receptionist,
)
from .models import Appointment, Invoice, InvoiceLineItem, PaymentTransaction
from .serializers import (
    AppointmentSerializer,
    InvoiceLineItemSerializer,
    InvoiceSerializer,
    PaymentTransactionSerializer,
)


def ledger_prefetches(request, prefix=''):
    """Batch both ledger actors and their selected-clinic membership metadata."""
    clinic = clinic_for(request)
    return (
        Prefetch(
            prefix + 'line_items',
            queryset=InvoiceLineItem.objects.select_related('created_by').prefetch_related(
                membership_prefetch(clinic, 'created_by__clinic_memberships'),
            ),
        ),
        Prefetch(
            prefix + 'transactions',
            queryset=PaymentTransaction.objects.select_related('recorded_by').prefetch_related(
                membership_prefetch(clinic, 'recorded_by__clinic_memberships'),
            ),
        ),
    )


def invoice_queryset_for(request):
    user = request.user
    queryset = Invoice.objects.filter(clinic=clinic_for(request), appointment__clinic=clinic_for(request)).select_related(
        'appointment__dentist', 'appointment__patient'
    ).prefetch_related(
        *ledger_prefetches(request)
    )
    if is_dentist(request) and not is_clinic_admin(request):
        return queryset.filter(appointment__dentist=user)
    if is_clinic_admin(request) or is_receptionist(request):
        return queryset
    return queryset.none()


class AppointmentListCreateView(generics.ListCreateAPIView):
    serializer_class = AppointmentSerializer
    permission_classes = [AppointmentAccessPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AppointmentFilter
    search_fields = ['patient__full_name', 'dentist__first_name', 'chief_complaint']
    ordering_fields = ['date_time', 'created_at']

    def get_queryset(self):
        """
        select_related fetches related objects in ONE query instead of many.
        Without it, accessing appointment.patient triggers a new DB query
        for every single appointment in the list — this is called the N+1 problem.
        """
        queryset = Appointment.objects.filter(clinic=clinic_for(self.request), patient__clinic=clinic_for(self.request)).select_related(
            'patient', 'dentist', 'invoice'
        ).prefetch_related(
            membership_prefetch(clinic_for(self.request), 'dentist__clinic_memberships'),
            *ledger_prefetches(self.request, 'invoice__'),
        ).all()
        if is_dentist(self.request) and not is_clinic_admin(self.request):
            queryset = queryset.filter(dentist=self.request.user)
        elif not (
            is_clinic_admin(self.request)
            or is_receptionist(self.request)
        ):
            queryset = queryset.none()
        return queryset

    def perform_create(self, serializer):
        """Serialize bookings for one dentist and recheck under the lock."""
        with transaction.atomic():
            dentist = CustomUser.objects.select_for_update().get(
                pk=serializer.validated_data['dentist'].pk
            )
            date_time = serializer.validated_data['date_time']
            duration = serializer.validated_data.get(
                'duration_minutes', Appointment.DEFAULT_DURATION_MINUTES
            )
            is_emergency = serializer.validated_data.get(
                'is_emergency_overbook', False
            )
            if not is_emergency and AppointmentSerializer.find_schedule_conflicts(
                    dentist, date_time, duration):
                raise ValidationError({
                    'date_time': 'This appointment overlaps another scheduled visit for this dentist.'
                })
            serializer.save(created_by=self.request.user, dentist=dentist, clinic=clinic_for(self.request))


class AppointmentDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = AppointmentSerializer
    permission_classes = [AppointmentAccessPermission]

    def get_queryset(self):
        queryset = Appointment.objects.filter(clinic=clinic_for(self.request), patient__clinic=clinic_for(self.request)).select_related(
            'patient', 'dentist', 'invoice'
        ).prefetch_related(
            membership_prefetch(clinic_for(self.request), 'dentist__clinic_memberships'),
            *ledger_prefetches(self.request, 'invoice__'),
        )
        if is_dentist(self.request) and not is_clinic_admin(self.request):
            return queryset.filter(dentist=self.request.user)
        if is_clinic_admin(self.request) or is_receptionist(self.request):
            return queryset
        return queryset.none()

    def perform_update(self, serializer):
        dentist = serializer.validated_data.get('dentist', serializer.instance.dentist)
        date_time = serializer.validated_data.get('date_time', serializer.instance.date_time)
        duration = serializer.validated_data.get(
            'duration_minutes', serializer.instance.duration_minutes
        )
        appointment_status = serializer.validated_data.get(
            'status', serializer.instance.status
        )
        is_emergency = serializer.validated_data.get(
            'is_emergency_overbook', serializer.instance.is_emergency_overbook
        )
        with transaction.atomic():
            dentist = CustomUser.objects.select_for_update().get(pk=dentist.pk)
            # Share this lock with X-ray attachment: neither operation may leave
            # the image pointing at a different patient's appointment.
            serializer.instance = Appointment.objects.select_for_update().get(
                pk=serializer.instance.pk,
            )
            patient = serializer.validated_data.get('patient', serializer.instance.patient)
            if serializer.instance.xrays.exclude(patient_id=patient.pk).exists():
                raise ValidationError({
                    'patient': 'The patient cannot change while this appointment has X-rays for another patient.'
                })
            if (
                appointment_status == 'scheduled'
                and not is_emergency
                and AppointmentSerializer.find_schedule_conflicts(
                    dentist, date_time, duration, serializer.instance
                )
            ):
                raise ValidationError({
                    'date_time': 'This appointment overlaps another scheduled visit for this dentist.'
                })
            serializer.save(dentist=dentist)


class InvoiceDetailView(generics.RetrieveUpdateAPIView):
    """
    GET   /api/appointments/<id>/invoice/  → view invoice
    PATCH /api/appointments/<id>/invoice/  → update payment
    No create — invoice is auto-created by signal.
    No delete — financial records should never be deleted.
    """
    serializer_class = InvoiceSerializer
    permission_classes = [InvoiceAccessPermission]

    def get_queryset(self):
        return invoice_queryset_for(self.request)

    def get_object(self):
        invoice = get_object_or_404(
            self.get_queryset(),
            appointment_id=self.kwargs['pk'],
        )
        self.check_object_permissions(self.request, invoice)
        return invoice


class InvoiceLineItemListCreateView(generics.ListCreateAPIView):
    serializer_class = InvoiceLineItemSerializer
    permission_classes = [InvoiceAccessPermission]

    def get_invoice(self, lock=False):
        queryset = invoice_queryset_for(self.request)
        if lock:
            queryset = queryset.select_for_update()
        invoice = get_object_or_404(
            queryset, appointment_id=self.kwargs['pk']
        )
        self.check_object_permissions(self.request, invoice)
        return invoice

    def get_queryset(self):
        return InvoiceLineItem.objects.filter(
            clinic=clinic_for(self.request),
            invoice=self.get_invoice()
        ).select_related('created_by').prefetch_related(
            membership_prefetch(clinic_for(self.request), 'created_by__clinic_memberships'),
        )

    def perform_create(self, serializer):
        with transaction.atomic():
            invoice = self.get_invoice(lock=True)
            serializer.save(invoice=invoice, created_by=self.request.user, clinic=invoice.clinic)


class InvoiceLineItemDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = InvoiceLineItemSerializer
    permission_classes = [InvoiceAccessPermission]
    lookup_url_kwarg = 'item_pk'

    def get_queryset(self):
        return InvoiceLineItem.objects.filter(
            clinic=clinic_for(self.request),
            invoice__in=invoice_queryset_for(self.request),
            invoice__appointment_id=self.kwargs['pk'],
        ).select_related('invoice__appointment', 'created_by').prefetch_related(
            membership_prefetch(clinic_for(self.request), 'created_by__clinic_memberships'),
        )

    def _lock_invoice_without_transactions(self, item):
        invoice = Invoice.objects.select_for_update().get(pk=item.invoice_id)
        if invoice.transactions.exists():
            raise ValidationError({
                'detail': 'Line items cannot change after a payment or refund is recorded.'
            })
        return invoice

    def perform_update(self, serializer):
        with transaction.atomic():
            self._lock_invoice_without_transactions(serializer.instance)
            serializer.save()

    def perform_destroy(self, instance):
        with transaction.atomic():
            self._lock_invoice_without_transactions(instance)
            instance.delete()


class PaymentTransactionListCreateView(generics.ListCreateAPIView):
    serializer_class = PaymentTransactionSerializer
    permission_classes = [InvoiceAccessPermission]

    def get_invoice(self, lock=False):
        queryset = invoice_queryset_for(self.request)
        if lock:
            queryset = queryset.select_for_update()
        invoice = get_object_or_404(
            queryset, appointment_id=self.kwargs['pk']
        )
        self.check_object_permissions(self.request, invoice)
        return invoice

    def get_queryset(self):
        return PaymentTransaction.objects.filter(
            clinic=clinic_for(self.request),
            invoice=self.get_invoice()
        ).select_related('recorded_by').prefetch_related(
            membership_prefetch(clinic_for(self.request), 'recorded_by__clinic_memberships'),
        )

    def perform_create(self, serializer):
        with transaction.atomic():
            invoice = self.get_invoice(lock=True)
            transaction_type = serializer.validated_data['transaction_type']
            amount = serializer.validated_data['amount']

            if transaction_type == PaymentTransaction.TYPE_PAYMENT:
                if invoice.appointment.status == 'cancelled':
                    raise ValidationError({
                        'transaction_type': 'Payments cannot be recorded for a cancelled appointment.'
                    })
                if invoice.total <= 0:
                    raise ValidationError({
                        'amount': 'Add at least one invoice line item before recording payment.'
                    })
                if amount > invoice.balance:
                    raise ValidationError({
                        'amount': 'Payment cannot exceed the outstanding balance.'
                    })
            elif amount > invoice.net_paid:
                raise ValidationError({
                    'amount': 'Refund cannot exceed the net amount collected.'
                })

            serializer.save(invoice=invoice, recorded_by=self.request.user, clinic=invoice.clinic)
