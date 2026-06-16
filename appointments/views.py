from rest_framework import generics, permissions
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import Appointment, Invoice
from .serializers import AppointmentSerializer, InvoiceSerializer


class AppointmentListCreateView(generics.ListCreateAPIView):
    serializer_class = AppointmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'dentist', 'patient']  # /api/appointments/?status=completed
    search_fields = ['patient__full_name', 'dentist__first_name', 'chief_complaint']
    ordering_fields = ['date_time', 'created_at']

    def get_queryset(self):
        """
        select_related fetches related objects in ONE query instead of many.
        Without it, accessing appointment.patient triggers a new DB query
        for every single appointment in the list — this is called the N+1 problem.
        """
        return Appointment.objects.select_related(
            'patient', 'dentist', 'invoice'
        ).all()

    def perform_create(self, serializer):
        """Automatically set created_by to the logged-in user."""
        serializer.save(created_by=self.request.user)


class AppointmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AppointmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Appointment.objects.select_related('patient', 'dentist', 'invoice')


class InvoiceDetailView(generics.RetrieveUpdateAPIView):
    """
    GET   /api/appointments/<id>/invoice/  → view invoice
    PATCH /api/appointments/<id>/invoice/  → update payment
    No create — invoice is auto-created by signal.
    No delete — financial records should never be deleted.
    """
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return Invoice.objects.get(appointment_id=self.kwargs['pk'])