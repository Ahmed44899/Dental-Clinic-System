from rest_framework import serializers
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
    