# appointments/serializers.py

from rest_framework import serializers
from .models import Appointment, Invoice
from patients.serializers import PatientSerializer
from accounts.serializers import UserSerializer
from accounts.models import CustomUser


class DentistField(serializers.PrimaryKeyRelatedField):
    """
    Custom relational field that only allows users with role='dentist'
    to be selected. Receptionists and admins are excluded automatically.
    """
    def get_queryset(self):
        return CustomUser.objects.filter(role='dentist')

class InvoiceSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            'id', 'total_fees', 'amount_paid', 'balance',
            'payment_method', 'payment_date', 'status', 'notes'
        ]
        read_only_fields = ['id', 'balance']

    def validate(self, data):
        """
        Object-level validation — runs after all field-level validation.
        Use this when validation involves more than one field at once.
        """
        total = data.get('total_fees', self.instance.total_fees if self.instance else 0)
        paid = data.get('amount_paid', self.instance.amount_paid if self.instance else 0)

        if paid > total:
            raise serializers.ValidationError("Amount paid cannot exceed total fees.")

        # Auto-set status based on payment
        if paid == 0:
            data['status'] = 'unpaid'
        elif paid < total:
            data['status'] = 'partial'
        else:
            data['status'] = 'paid'

        return data


class AppointmentSerializer(serializers.ModelSerializer):
    # Nested read — shows full patient/dentist data in GET responses
    patient_detail = PatientSerializer(source='patient', read_only=True)
    dentist_detail = UserSerializer(source='dentist', read_only=True)
    dentist = DentistField()
    # Nested write — invoice is shown inside appointment response
    invoice = InvoiceSerializer(read_only=True)

    class Meta:
        model = Appointment
        fields = [
            'id', 'patient', 'patient_detail',
            'dentist', 'dentist_detail',
            'date_time', 'chief_complaint', 'diagnosis',
            'procedures_done', 'notes', 'status',
            'invoice', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']

    def validate_date_time(self, value):
        """Prevent scheduling appointments in the past."""
        from django.utils import timezone
        if value < timezone.now():
            raise serializers.ValidationError("Appointment cannot be scheduled in the past.")
        return value