from rest_framework import generics, permissions, filters
from .models import CustomUser
from .serializers import UserSerializer
from .permissions import IsClinicAdmin


class RegisterUserView(generics.CreateAPIView):
    """Only admins can create new staff accounts."""
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsClinicAdmin]


class StaffListView(generics.ListAPIView):
    """List all staff members. Auth required."""
    queryset = CustomUser.objects.all().order_by('role')
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]


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
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['first_name', 'last_name', 'specialization']

    def get_queryset(self):
        return CustomUser.objects.filter(role='dentist').only(
            'id', 'first_name', 'last_name', 'specialization'
        )
