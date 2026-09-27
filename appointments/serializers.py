from clinics.api import clinic_for
from patients.models import PatientProfile

# appointments/serializers.py

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers
from .models import Appointment, Invoice, InvoiceLineItem, PaymentTransaction
from patients.serializers import PatientSerializer
from accounts.serializers import StaffDirectorySerializer
from accounts.models import CustomUser
from accounts.permissions import is_dentist, is_receptionist


class DentistField(serializers.PrimaryKeyRelatedField):
    """
    Custom relational field that only allows users with role='dentist'
    to be selected. Receptionists and admins are excluded automatically.
    """
    def get_queryset(self):
        request = self.context.get('request')
        if request is None:
            return CustomUser.objects.none()
        return CustomUser.objects.filter(
            is_active=True, clinic_memberships__clinic=clinic_for(request),
            clinic_memberships__role='dentist', clinic_memberships__is_active=True,
        )

class InvoiceLineItemSerializer(serializers.ModelSerializer):
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    created_by = StaffDirectorySerializer(read_only=True)

    class Meta:
        model = InvoiceLineItem
        fields = [
            'id', 'description', 'procedure_code', 'quantity', 'unit_price',
            'total', 'created_by', 'created_at',
        ]
        read_only_fields = ['id', 'total', 'created_by', 'created_at']

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError('Quantity must be greater than zero.')
        return value

    def validate_unit_price(self, value):
        if value < 0:
            raise serializers.ValidationError('Unit price cannot be negative.')
        return value


class PaymentTransactionSerializer(serializers.ModelSerializer):
    recorded_by = StaffDirectorySerializer(read_only=True)
    occurred_at = serializers.DateTimeField(default=timezone.now)

    class Meta:
        model = PaymentTransaction
        fields = [
            'id', 'transaction_type', 'amount', 'payment_method',
            'reference', 'notes', 'occurred_at', 'recorded_by', 'recorded_at',
        ]
        read_only_fields = ['id', 'recorded_by', 'recorded_at']

    def validate_amount(self, value):
        if value <= Decimal('0.00'):
            raise serializers.ValidationError('Transaction amount must be positive.')
        return value

    def validate_occurred_at(self, value):
        if value > timezone.now() + timedelta(minutes=5):
            raise serializers.ValidationError('Transaction date cannot be in the future.')
        return value


class InvoiceSerializer(serializers.ModelSerializer):
    appointment_status = serializers.CharField(source='appointment.status', read_only=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    payments_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    refunds_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    net_paid = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    status = serializers.CharField(read_only=True)
    line_items = InvoiceLineItemSerializer(many=True, read_only=True)
    transactions = PaymentTransactionSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            'id', 'appointment_status', 'currency', 'total', 'payments_total', 'refunds_total',
            'net_paid', 'balance', 'status', 'notes',
            'line_items', 'transactions',
        ]
        read_only_fields = [
            'id', 'total', 'payments_total', 'refunds_total', 'net_paid',
            'balance', 'status', 'line_items', 'transactions',
        ]

    def validate(self, data):
        if (
            self.instance
            and 'currency' in data
            and data['currency'] != self.instance.currency
            and (
                self.instance.line_items.exists()
                or self.instance.transactions.exists()
            )
        ):
            raise serializers.ValidationError({
                'currency': 'Currency cannot change after financial activity begins.'
            })
        return data


class AppointmentSerializer(serializers.ModelSerializer):
    # Nested read — shows full patient/dentist data in GET responses
    patient_detail = PatientSerializer(source='patient', read_only=True)
    dentist_detail = StaffDirectorySerializer(source='dentist', read_only=True)
    dentist = DentistField()
    # Nested write — invoice is shown inside appointment response
    invoice = InvoiceSerializer(read_only=True)

    class Meta:
        model = Appointment
        validators = []
        fields = [
            'id', 'patient', 'patient_detail',
            'dentist', 'dentist_detail',
            'date_time', 'duration_minutes',
            'is_emergency_overbook', 'emergency_reason',
            'chief_complaint', 'diagnosis',
            'procedures_done', 'notes', 'status',
            'invoice', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        self.fields['patient'].queryset = (
            PatientProfile.objects.filter(clinic=clinic_for(request))
            if request else PatientProfile.objects.none()
        )

    def validate_date_time(self, value):
        """Prevent scheduling appointments in the past."""
        if value < timezone.now():
            raise serializers.ValidationError("Appointment cannot be scheduled in the past.")
        return value

    def validate_duration_minutes(self, value):
        if not Appointment.MIN_DURATION_MINUTES <= value <= Appointment.MAX_DURATION_MINUTES:
            raise serializers.ValidationError(
                'Appointment duration must be between 5 minutes and 8 hours.'
            )
        return value

    @staticmethod
    def find_schedule_conflicts(dentist, date_time, duration_minutes, instance=None):
        """Return scheduled visits whose half-open time ranges overlap."""
        end_time = date_time + timedelta(minutes=duration_minutes)
        possible = Appointment.objects.filter(
            dentist=dentist,
            status='scheduled',
            date_time__lt=end_time,
        )
        if instance:
            possible = possible.exclude(pk=instance.pk)
        return [
            appointment
            for appointment in possible.only('id', 'date_time', 'duration_minutes')
            if appointment.date_time + timedelta(
                minutes=appointment.duration_minutes
            ) > date_time
        ]

    def validate(self, data):
        request = self.context.get('request')
        submitted_fields = set(self.initial_data.keys())

        if request and is_receptionist(request):
            protected_fields = {'diagnosis', 'procedures_done'}
            attempted_fields = protected_fields.intersection(submitted_fields)
            if attempted_fields:
                raise serializers.ValidationError({
                    field: 'Receptionists may view but not modify clinical outcomes.'
                    for field in sorted(attempted_fields)
                })

        if request and is_dentist(request) and self.instance:
            scheduling_fields = {
                'patient', 'dentist', 'date_time', 'duration_minutes',
                'is_emergency_overbook', 'emergency_reason',
            }
            attempted_fields = scheduling_fields.intersection(submitted_fields)
            if attempted_fields:
                raise serializers.ValidationError({
                    field: 'Dentists may not reassign or reschedule appointments.'
                    for field in sorted(attempted_fields)
                })

        dentist = data.get('dentist', getattr(self.instance, 'dentist', None))
        date_time = data.get('date_time', getattr(self.instance, 'date_time', None))
        duration = data.get(
            'duration_minutes',
            getattr(self.instance, 'duration_minutes', Appointment.DEFAULT_DURATION_MINUTES),
        )
        status = data.get('status', getattr(self.instance, 'status', 'scheduled'))
        is_emergency = data.get(
            'is_emergency_overbook',
            getattr(self.instance, 'is_emergency_overbook', False),
        )
        emergency_reason = data.get(
            'emergency_reason',
            getattr(self.instance, 'emergency_reason', ''),
        )

        if (
            dentist
            and not dentist.is_active
            and (self.instance is None or 'dentist' in submitted_fields)
        ):
            raise serializers.ValidationError({
                'dentist': 'Appointments cannot be assigned to an inactive dentist.'
            })

        if self.instance is None and status != 'scheduled':
            raise serializers.ValidationError({
                'status': 'New appointments must begin as scheduled.'
            })

        if is_emergency and not emergency_reason.strip():
            raise serializers.ValidationError({
                'emergency_reason': 'Explain why this emergency must be overbooked.'
            })
        if not is_emergency:
            data['emergency_reason'] = ''

        if self.instance:
            previous_status = self.instance.status
            terminal_statuses = {'completed', 'cancelled', 'no_show'}
            if previous_status in terminal_statuses and status != previous_status:
                raise serializers.ValidationError({
                    'status': f'A {previous_status.replace("_", " ")} appointment cannot be reopened.'
                })
            if previous_status in terminal_statuses:
                protected = {
                    'patient', 'dentist', 'date_time', 'duration_minutes',
                    'is_emergency_overbook', 'emergency_reason',
                }
                attempted = protected.intersection(submitted_fields)
                if attempted:
                    raise serializers.ValidationError({
                        field: 'Scheduling details cannot change after a visit is closed.'
                        for field in sorted(attempted)
                    })

        if status in {'completed', 'no_show'} and date_time > timezone.now():
            raise serializers.ValidationError({
                'status': 'A future appointment cannot be completed or marked as no-show.'
            })

        if dentist and date_time and status == 'scheduled' and not is_emergency:
            conflicts = self.find_schedule_conflicts(
                dentist, date_time, duration, self.instance
            )
            if conflicts:
                raise serializers.ValidationError({
                    'date_time': 'This appointment overlaps another scheduled visit for this dentist.'
                })
        return data
