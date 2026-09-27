from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, filters, status
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from clinics.api import HasClinicMembership, clinic_for
from clinics.models import Clinic, ClinicMembership
from clinics.querysets import membership_prefetch
from .models import CustomUser
from .serializers import (
    LogoutSerializer, PasswordChangeSerializer, StaffDirectorySerializer,
    MembershipStatusSerializer, UserSerializer,
)
from .permissions import IsClinicAdmin, is_clinic_admin


class LoginView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'


class RefreshTokenView(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'token_refresh'


class MembershipListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        memberships = ClinicMembership.objects.filter(
            user=request.user, user__is_active=True,
            is_active=True, clinic__is_active=True,
        ).select_related('clinic').order_by('clinic__name', 'pk')
        return Response([
            {'clinic_id': m.clinic_id, 'clinic_name': m.clinic.name, 'role': m.role}
            for m in memberships
        ])


class RegisterUserView(generics.CreateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsClinicAdmin]

    def perform_create(self, serializer):
        with transaction.atomic():
            user = serializer.save()
            ClinicMembership.objects.create(
                user=user, clinic=clinic_for(self.request), role=user.role,
            )


class StaffListView(generics.ListAPIView):
    serializer_class = StaffDirectorySerializer
    permission_classes = [HasClinicMembership]

    def get_queryset(self):
        membership_filters = {'clinic_memberships__clinic': clinic_for(self.request)}
        if not is_clinic_admin(self.request):
            membership_filters.update(is_active=True, clinic_memberships__is_active=True)
        # Keep reverse-relation predicates in one filter so they match the same
        # membership row, not an active membership in a different clinic.
        return CustomUser.objects.filter(**membership_filters).order_by('username').prefetch_related(
            membership_prefetch(clinic_for(self.request)),
        )


class CurrentUserView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [HasClinicMembership]

    def get_object(self):
        return self.request.user


class DentistListView(generics.ListAPIView):
    serializer_class = StaffDirectorySerializer
    permission_classes = [HasClinicMembership]
    filter_backends = [filters.SearchFilter]
    search_fields = ['first_name', 'last_name', 'specialization']

    def get_queryset(self):
        return CustomUser.objects.filter(
            is_active=True, clinic_memberships__clinic=clinic_for(self.request),
            clinic_memberships__role='dentist', clinic_memberships__is_active=True,
        ).prefetch_related(membership_prefetch(clinic_for(self.request)))


class LogoutView(generics.GenericAPIView):
    serializer_class = LogoutSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_205_RESET_CONTENT)


class PasswordChangeView(generics.GenericAPIView):
    serializer_class = PasswordChangeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'detail': 'Password changed. Sign in again on every device.'},
            status=status.HTTP_200_OK,
        )


class StaffStatusView(generics.UpdateAPIView):
    serializer_class = MembershipStatusSerializer
    permission_classes = [IsClinicAdmin]
    http_method_names = ['patch', 'options']

    def get_object(self):
        return get_object_or_404(
            ClinicMembership.objects.select_related('user'),
            clinic=clinic_for(self.request), user_id=self.kwargs['pk'],
        )

    def perform_update(self, serializer):
        with transaction.atomic():
            # Serialize membership deactivations within this clinic.
            Clinic.objects.select_for_update().get(pk=clinic_for(self.request).pk)
            if not serializer.validated_data.get('is_active', serializer.instance.is_active):
                if serializer.instance.user_id == self.request.user.pk:
                    raise ValidationError({'is_active': 'You cannot deactivate your own membership.'})
                if serializer.instance.role == 'admin' and not ClinicMembership.objects.filter(
                    clinic=clinic_for(self.request), role='admin',
                    is_active=True, user__is_active=True,
                ).exclude(pk=serializer.instance.pk).exists():
                    raise ValidationError({'is_active': 'Keep at least one active clinic administrator.'})
            serializer.save()
