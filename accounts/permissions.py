from rest_framework.permissions import BasePermission, SAFE_METHODS


def is_clinic_admin(user):
    """Return True for either Django administrators or clinic-role admins."""
    return bool(
        user
        and user.is_authenticated
        and (user.is_staff or user.is_superuser or user.role == 'admin')
    )


def is_receptionist(user):
    return bool(user and user.is_authenticated and user.role == 'receptionist')


def is_dentist(user):
    return bool(user and user.is_authenticated and user.role == 'dentist')


def dentist_has_patient(user, patient_id):
    """Define dentist/patient ownership through an assigned appointment."""
    if not is_dentist(user) or not patient_id:
        return False

    # Imported lazily to avoid an accounts -> appointments import cycle.
    from appointments.models import Appointment
    return Appointment.objects.filter(
        dentist_id=user.pk,
        patient_id=patient_id,
    ).exists()


class IsClinicAdmin(BasePermission):
    """Allow Django staff/superusers and users assigned the clinic admin role."""

    def has_permission(self, request, view):
        return is_clinic_admin(request.user)


class PatientAccessPermission(BasePermission):
    """Staff can read patients; only admin/reception can create records."""

    message = 'Your clinic role does not allow this patient-record action.'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method == 'POST':
            return is_clinic_admin(user) or is_receptionist(user)
        return is_clinic_admin(user) or is_receptionist(user) or is_dentist(user)

    def has_object_permission(self, request, view, obj):
        # Patient deletion is not exposed by the views. All three clinic roles
        # may read/update existing records; serializers protect specific fields.
        return self.has_permission(request, view)


class AppointmentAccessPermission(BasePermission):
    """Reception/admin schedule globally; dentists access assigned visits."""

    message = 'Dentists may only access appointments assigned to them.'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method == 'POST':
            return is_clinic_admin(user) or is_receptionist(user)
        return is_clinic_admin(user) or is_receptionist(user) or is_dentist(user)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if is_clinic_admin(user) or is_receptionist(user):
            return True
        return is_dentist(user) and obj.dentist_id == user.pk


class InvoiceAccessPermission(BasePermission):
    """Dentists may view their invoices; reception/admin may edit them."""

    message = 'Your clinic role does not allow this invoice action.'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method not in SAFE_METHODS:
            return is_clinic_admin(user) or is_receptionist(user)
        return is_clinic_admin(user) or is_receptionist(user) or is_dentist(user)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if is_clinic_admin(user) or is_receptionist(user):
            return True
        appointment = getattr(obj, 'appointment', None)
        if appointment is None and getattr(obj, 'invoice', None):
            appointment = obj.invoice.appointment
        return (
            request.method in SAFE_METHODS
            and is_dentist(user)
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
            and (is_clinic_admin(user) or is_receptionist(user) or is_dentist(user))
        )

    def has_object_permission(self, request, view, obj):
        user = request.user
        if is_clinic_admin(user):
            return True
        if is_receptionist(user):
            return request.method in SAFE_METHODS
        if is_dentist(user):
            return dentist_has_patient(user, obj.patient_id)
        return False
