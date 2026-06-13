from rest_framework import serializers
from .models import CustomUser


class UserSerializer(serializers.ModelSerializer):
    # write_only=True means password appears in requests but NEVER in responses
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'first_name', 'last_name',
                  'role', 'phone', 'specialization', 'license_number', 'password']
        # These fields can be read but never written through the API
        read_only_fields = ['id']

    def create(self, validated_data):
        # NEVER save a raw password — always use set_password() which hashes it
        password = validated_data.pop('password')
        user = CustomUser(**validated_data)
        user.set_password(password)
        user.save()
        return user