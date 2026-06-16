# patients/views.py

from rest_framework import generics, permissions, filters
from .models import PatientProfile
from .serializers import PatientSerializer


class PatientListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/patients/        → list all patients (with search)
    POST /api/patients/        → create new patient
    """
    queryset = PatientProfile.objects.all()
    serializer_class = PatientSerializer
    permission_classes = [permissions.IsAuthenticated]

    # Built-in DRF search — lets you do /api/patients/?search=ahmed
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['full_name', 'phone', 'email']
    ordering_fields = ['full_name', 'created_at']


class PatientDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/patients/<id>/  → get one patient
    PUT    /api/patients/<id>/  → update fully
    PATCH  /api/patients/<id>/  → update partially
    DELETE /api/patients/<id>/  → delete
    """
    queryset = PatientProfile.objects.all()
    serializer_class = PatientSerializer
    permission_classes = [permissions.IsAuthenticated]


class PatientSearchView(generics.ListAPIView):
    """
    Lightweight endpoint just for searching patients when booking.
    Returns only the fields needed to identify a patient.
    GET /api/patients/search/?q=ahmed
    """
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['full_name', 'phone']

    def get_queryset(self):
        return PatientProfile.objects.only('id', 'full_name', 'phone', 'date_of_birth')

    def get_serializer_class(self):
        from rest_framework import serializers

        class PatientSearchSerializer(serializers.ModelSerializer):
            class Meta:
                model = PatientProfile
                fields = ['id', 'full_name', 'phone', 'date_of_birth']

        return PatientSearchSerializer
    