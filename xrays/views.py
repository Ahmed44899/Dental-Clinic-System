from rest_framework import generics, permissions
from .models import XRay
from .serializers import XRaySerializer


class XRayListCreateView(generics.ListCreateAPIView):
    serializer_class = XRaySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Filter by patient — /api/xrays/?patient=3
        A patient's full xray history in one call.
        """
        queryset = XRay.objects.select_related('patient', 'appointment')
        patient_id = self.request.query_params.get('patient')
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        return queryset


class XRayDetailView(generics.RetrieveDestroyAPIView):
    """No update — xray records should not be modified after creation."""
    queryset = XRay.objects.select_related('patient', 'appointment')
    serializer_class = XRaySerializer
    permission_classes = [permissions.IsAuthenticated]
