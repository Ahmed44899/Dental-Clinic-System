from rest_framework.permissions import BasePermission, SAFE_METHODS
from clinics.api import membership_for, clinic_for, HasClinicMembership


def is_clinic_admin(request):
    return membership_for(request).role == 'admin'


def is_receptionist(request):
    return membership_for(request).role == 'receptionist'


def is_dentist(request):
    return membership_for(request).role == 'dentist'


def dentist_has_patient(request, patient_id):
    """Define dentist/patient ownership through an assigned appointment."""
    if not is_dentist(request) or not patient_id:
        return False

    # Imported lazily to avoid an accounts -> appointments import cycle.
    from appointments.models import Appointment
    return Appointment.objects.filter(
        dentist_id=request.user.pk,
        clinic=clinic_for(request),
        patient_id=patient_id,
    ).exists()


class IsClinicAdmin(BasePermission):
    """Allow administrators of the selected clinic."""

    def has_permission(self, request, view):
        return HasClinicMembership().has_permission(request, view) and is_clinic_admin(request)


class PatientAccessPermission(BasePermission):
    """Staff can read patients; only admin/reception can create records."""

    message = 'Your clinic role does not allow this patient-record action.'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method == 'POST':
            return is_clinic_admin(request) or is_receptionist(request)
        return is_clinic_admin(request) or is_receptionist(request) or is_dentist(request)

    def has_object_permission(self, request, view, obj):
        if obj.clinic_id != clinic_for(request).pk:
            return False
        # Patient deletion is not exposed by the views. All three clinic roles
        # may read/update existing records; serializers protect specific fields.
        return self.has_permission(request, view)


class AppointmentAccessPermission(BasePermission):
    """Reception/admin schedule within a clinic; dentists access assigned visits."""

    message = 'Dentists may only access appointments assigned to them.'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method == 'POST':
            return is_clinic_admin(request) or is_receptionist(request)
        return is_clinic_admin(request) or is_receptionist(request) or is_dentist(request)

    def has_object_permission(self, request, view, obj):
        if obj.clinic_id != clinic_for(request).pk:
            return False
        user = request.user
        if is_clinic_admin(request) or is_receptionist(request):
            return True
        return is_dentist(request) and obj.dentist_id == user.pk


class InvoiceAccessPermission(BasePermission):
    """Dentists may view their invoices; reception/admin may edit them."""

    message = 'Your clinic role does not allow this invoice action.'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method not in SAFE_METHODS:
            return is_clinic_admin(request) or is_receptionist(request)
        return is_clinic_admin(request) or is_receptionist(request) or is_dentist(request)

    def has_object_permission(self, request, view, obj):
        if obj.clinic_id != clinic_for(request).pk:
            return False
        user = request.user
        if is_clinic_admin(request) or is_receptionist(request):
            return True
        appointment = getattr(obj, 'appointment', None)
        if appointment is None and getattr(obj, 'invoice', None):
            appointment = obj.invoice.appointment
        return (
            request.method in SAFE_METHODS
            and is_dentist(request)
            and appointment is not None
            and appointment.dentist_id == user.pk
        )


class XRayAccessPermission(BasePermission):
    """Dentists access their patients' images; only admin/dentist may delete."""

    message = 'Your clinic role does not allow this X-ray action.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (is_clinic_admin(request) or is_receptionist(request) or is_dentist(request))
        )

    def has_object_permission(self, request, view, obj):
        if obj.clinic_id != clinic_for(request).pk:
            return False
        user = request.user
        if is_clinic_admin(request):
            return True
        if is_receptionist(request):
            return request.method in SAFE_METHODS
        if is_dentist(request):
            return dentist_has_patient(request, obj.patient_id)
        return False
