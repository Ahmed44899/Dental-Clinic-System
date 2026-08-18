from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from .models import CustomUser


class UserSerializer(serializers.ModelSerializer):
    # write_only=True means password appears in requests but NEVER in responses
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'first_name', 'last_name',
                  'role', 'phone', 'specialization', 'license_number',
                  'is_staff', 'password']
        # These fields can be read but never written through the API
        read_only_fields = ['id', 'is_staff']

    def validate(self, data):
        password = data.get('password')
        if password:
            candidate = self.instance or CustomUser(
                username=data.get('username', ''),
                email=data.get('email', ''),
                first_name=data.get('first_name', ''),
                last_name=data.get('last_name', ''),
            )
            try:
                password_validation.validate_password(password, candidate)
            except DjangoValidationError as error:
                raise serializers.ValidationError({'password': list(error.messages)})
        return data

    def create(self, validated_data):
        # NEVER save a raw password — always use set_password() which hashes it
        password = validated_data.pop('password')
        return CustomUser.objects.create_user(password=password, **validated_data)


class StaffDirectorySerializer(serializers.ModelSerializer):
    """Small, non-sensitive staff representation for authenticated coworkers."""

    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'first_name', 'last_name',
            'role', 'specialization', 'is_active',
        ]
        read_only_fields = fields


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)

    def validate_refresh(self, value):
        try:
            self.token = RefreshToken(value)
        except TokenError:
            raise serializers.ValidationError('This refresh token is invalid or expired.')
        return value

    def save(self, **kwargs):
        self.token.blacklist()


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_old_password(self, value):
        if not self.context['request'].user.check_password(value):
            raise serializers.ValidationError('The current password is incorrect.')
        return value

    def validate(self, data):
        if data['old_password'] == data['new_password']:
            raise serializers.ValidationError({
                'new_password': 'The new password must be different from the current password.'
            })
        try:
            password_validation.validate_password(
                data['new_password'],
                self.context['request'].user,
            )
        except DjangoValidationError as error:
            raise serializers.ValidationError({'new_password': list(error.messages)})
        return data

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password'])

        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)
        return user


class StaffStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'role', 'is_active']
        read_only_fields = ['id', 'username', 'role']

    def validate_is_active(self, value):
        request_user = self.context['request'].user
        if self.instance == request_user and not value:
            raise serializers.ValidationError('You cannot deactivate your own account.')
        if self.instance.is_superuser and not request_user.is_superuser:
            raise serializers.ValidationError('Only a superuser may change a superuser account.')
        return value
