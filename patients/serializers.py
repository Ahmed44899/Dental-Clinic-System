from rest_framework import serializers
from accounts.permissions import is_receptionist
from .models import PatientProfile


class PatientSerializer(serializers.ModelSerializer):
    # This comes from the @property on the model — read only, auto-calculated
    age = serializers.IntegerField(read_only=True)

    class Meta:
        model = PatientProfile
        fields = [
            'id', 'full_name', 'phone', 'email',
            'date_of_birth', 'age', 'blood_type',
            'allergies', 'medical_notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_phone(self, value):
        """
        Custom field validation — runs automatically when serializer.is_valid() is called.
        This is a pattern you'll use constantly in real projects.
        """
        if value and not value.replace('+', '').replace('-', '').replace(' ', '').isdigit():
            raise serializers.ValidationError("Phone number must contain only digits, +, or -.")
        return value

    def validate(self, data):
        request = self.context.get('request')
        protected_fields = {'allergies', 'medical_notes'}
        attempted_fields = protected_fields.intersection(self.initial_data.keys())

        if request and is_receptionist(request) and attempted_fields:
            raise serializers.ValidationError({
                field: 'Receptionists may view but not modify clinical information.'
                for field in sorted(attempted_fields)
            })
        return data
