from rest_framework import generics, permissions, filters, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .models import CustomUser
from .serializers import (
    LogoutSerializer,
    PasswordChangeSerializer,
    StaffDirectorySerializer,
    StaffStatusSerializer,
    UserSerializer,
)
from .permissions import IsClinicAdmin, is_clinic_admin


class LoginView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'


class RefreshTokenView(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'token_refresh'


class RegisterUserView(generics.CreateAPIView):
    """Only admins can create new staff accounts."""
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsClinicAdmin]


class StaffListView(generics.ListAPIView):
    """List all staff members. Auth required."""
    serializer_class = StaffDirectorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = CustomUser.objects.all().order_by('role')
        if is_clinic_admin(self.request.user):
            return queryset
        return queryset.filter(is_active=True)


class CurrentUserView(generics.RetrieveAPIView):
    """Return the signed-in staff member for role-aware clients."""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

class DentistListView(generics.ListAPIView):
    """
    GET /api/accounts/dentists/
    Returns only users with role='dentist' so receptionists
    can see who to assign appointments to.
    """
    serializer_class = StaffDirectorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['first_name', 'last_name', 'specialization']

    def get_queryset(self):
        return CustomUser.objects.filter(role='dentist', is_active=True).only(
            'id', 'username', 'first_name', 'last_name', 'role', 'specialization'
        )


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
    queryset = CustomUser.objects.all()
    serializer_class = StaffStatusSerializer
    permission_classes = [IsClinicAdmin]
    http_method_names = ['patch', 'options']
