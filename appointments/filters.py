import django_filters
from accounts.models import CustomUser
from clinics.api import clinic_for
from patients.models import PatientProfile
from .models import Appointment


def clinic_patients(request):
    if request is None:
        return PatientProfile.objects.none()
    return PatientProfile.objects.filter(clinic=clinic_for(request))


def clinic_dentists(request):
    if request is None:
        return CustomUser.objects.none()
    return CustomUser.objects.filter(
        clinic_memberships__clinic=clinic_for(request),
        clinic_memberships__role='dentist',
    )


class AppointmentFilter(django_filters.FilterSet):
    patient = django_filters.ModelChoiceFilter(queryset=clinic_patients)
    dentist = django_filters.ModelChoiceFilter(queryset=clinic_dentists)

    class Meta:
        model = Appointment
        fields = ['status', 'dentist', 'patient', 'is_emergency_overbook']
