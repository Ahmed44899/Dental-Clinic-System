from rest_framework.permissions import BasePermission
from .access import resolve_membership


def membership_for(request):
    if not hasattr(request, 'clinic_membership'):
        request.clinic_membership = resolve_membership(
            request.user, request.headers.get('X-Clinic-ID'),
        )
    return request.clinic_membership


def clinic_for(request):
    return membership_for(request).clinic


class HasClinicMembership(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        membership_for(request)
        return True
