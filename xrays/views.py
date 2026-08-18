import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import cloudinary.uploader
from cloudinary.utils import cloudinary_url
from django.http import FileResponse, HttpResponseRedirect
from rest_framework import generics
from rest_framework.exceptions import APIException, NotFound, PermissionDenied
from accounts.permissions import (
    XRayAccessPermission,
    dentist_has_patient,
    is_clinic_admin,
    is_dentist,
)
from .models import XRay
from .serializers import XRaySerializer


class XRayStorageError(APIException):
    status_code = 503
    default_detail = 'The X-ray storage service is unavailable. Please try again.'


def xray_queryset_for(user):
    queryset = XRay.objects.select_related('patient', 'appointment')
    if is_dentist(user) and not is_clinic_admin(user):
        queryset = queryset.filter(
            patient__appointments__dentist=user
        ).distinct()
    return queryset


class XRayListCreateView(generics.ListCreateAPIView):
    serializer_class = XRaySerializer
    permission_classes = [XRayAccessPermission]

    def get_queryset(self):
        """
        Filter by patient — /api/xrays/?patient=3
        A patient's full xray history in one call.
        """
        queryset = xray_queryset_for(self.request.user)
        patient_id = self.request.query_params.get('patient')
        appointment_id = self.request.query_params.get('appointment')
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        if appointment_id:
            queryset = queryset.filter(appointment_id=appointment_id)
        return queryset

    def perform_create(self, serializer):
        patient = serializer.validated_data['patient']
        appointment = serializer.validated_data.get('appointment')
        if (
            is_dentist(self.request.user)
            and not is_clinic_admin(self.request.user)
        ):
            if not dentist_has_patient(self.request.user, patient.pk):
                raise PermissionDenied(
                    'Dentists may upload X-rays only for their assigned patients.'
                )
            if appointment and appointment.dentist_id != self.request.user.pk:
                raise PermissionDenied(
                    'Dentists may attach X-rays only to their own appointments.'
                )
        serializer.save()


class XRayDetailView(generics.RetrieveDestroyAPIView):
    """No update — xray records should not be modified after creation."""
    queryset = XRay.objects.select_related('patient', 'appointment')
    serializer_class = XRaySerializer
    permission_classes = [XRayAccessPermission]

    def get_queryset(self):
        return xray_queryset_for(self.request.user)

    def perform_destroy(self, instance):
        """Remove owned storage objects before removing their database pointer."""
        try:
            if instance.cloud_public_id:
                cloudinary.uploader.destroy(
                    instance.cloud_public_id,
                    resource_type='image',
                    type='authenticated',
                    invalidate=True,
                )
            if instance.image_local:
                instance.image_local.delete(save=False)
        except Exception as exc:
            raise XRayStorageError() from exc
        instance.delete()


class XRayImageView(generics.GenericAPIView):
    """Serve an image only after applying the same record permissions."""

    permission_classes = [XRayAccessPermission]

    def get_queryset(self):
        return xray_queryset_for(self.request.user)

    def get(self, request, *args, **kwargs):
        xray = self.get_object()
        if xray.image_local:
            try:
                xray.image_local.open('rb')
            except (FileNotFoundError, OSError):
                pass
            else:
                content_type = mimetypes.guess_type(xray.image_local.name)[0]
                suffix = Path(xray.image_local.name).suffix.lower()
                response = FileResponse(
                    xray.image_local,
                    content_type=content_type or 'application/octet-stream',
                    as_attachment=False,
                    filename=f'xray-{xray.pk}{suffix}',
                )
                response['Cache-Control'] = 'private, no-store'
                response['X-Content-Type-Options'] = 'nosniff'
                response['Content-Security-Policy'] = "default-src 'none'; sandbox"
                return response

        cloud_url = ''
        if xray.cloud_public_id:
            cloud_url, _ = cloudinary_url(
                xray.cloud_public_id,
                resource_type='image',
                type='authenticated',
                sign_url=True,
                secure=True,
            )
        elif xray.image_cloud:
            cloud_url = xray.image_cloud

        if cloud_url and urlparse(cloud_url).scheme == 'https':
            response = HttpResponseRedirect(cloud_url)
            response['Cache-Control'] = 'private, no-store'
            return response
        raise NotFound('This X-ray image is not available in storage.')
