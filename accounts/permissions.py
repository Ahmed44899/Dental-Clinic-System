from rest_framework.permissions import BasePermission


class IsClinicAdmin(BasePermission):
    """Allow Django staff/superusers and users assigned the clinic admin role."""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_staff or user.is_superuser or user.role == 'admin')
        )
