from clinics.api import clinic_for
from clinics.models import ClinicMembership
from clinics.querysets import membership_cache_attr

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from .models import CustomUser


class ClinicUserRepresentationMixin:
    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        membership = None
        if request:
            clinic = clinic_for(request)
            cached = getattr(instance, membership_cache_attr(clinic.pk), None)
            if cached is not None:
                membership = next((m for m in cached if m.clinic_id == clinic.pk), None)
            else:
                # Single-object/write responses may not use a prefetched queryset.
                membership = instance.clinic_memberships.filter(clinic=clinic).first()
        data['role'] = membership.role if membership else None
        if 'is_active' in data:
            data['is_active'] = bool(instance.is_active and membership and membership.is_active)
        # Django admin privileges are never a clinic role.
        if 'is_staff' in data:
            data['is_staff'] = False
        return data


class UserSerializer(ClinicUserRepresentationMixin, serializers.ModelSerializer):
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


class StaffDirectorySerializer(ClinicUserRepresentationMixin, serializers.ModelSerializer):
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


class MembershipStatusSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user_id', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = ClinicMembership
        fields = ['id', 'username', 'role', 'is_active']
        read_only_fields = ['id', 'username', 'role']
