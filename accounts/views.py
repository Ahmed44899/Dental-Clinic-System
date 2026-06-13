from rest_framework import generics, permissions
from .models import CustomUser
from .serializers import UserSerializer


class RegisterUserView(generics.CreateAPIView):
    """Only admins can create new staff accounts."""
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]


class StaffListView(generics.ListAPIView):
    """List all staff members. Auth required."""
    queryset = CustomUser.objects.all().order_by('role')
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]