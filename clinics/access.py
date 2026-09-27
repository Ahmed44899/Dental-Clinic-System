from rest_framework.exceptions import PermissionDenied

from .models import ClinicMembership


def resolve_membership(user, clinic_id=None):
    # Resolve after authentication. Never trust a supplied clinic ID or JWT role
    # without checking current membership state in the database.
    if not user or not user.is_authenticated or not user.is_active:
        raise PermissionDenied('An active clinic membership is required.')

    memberships = ClinicMembership.objects.select_related('clinic').filter(
        user_id=user.pk, user__is_active=True,
        is_active=True, clinic__is_active=True,
    )
    if clinic_id is not None:
        value = str(clinic_id)
        if (
            len(value) > 19 or not value.isascii() or not value.isdecimal()
            or not 0 < int(value) <= 9223372036854775807
        ):
            raise PermissionDenied('An active clinic membership is required.')
        membership = memberships.filter(clinic_id=int(value)).first()
        if membership is None:
            raise PermissionDenied('An active clinic membership is required.')
        return membership

    candidates = list(memberships.order_by('pk')[:2])
    if len(candidates) != 1:
        raise PermissionDenied('Select a clinic with an active membership.')
    return candidates[0]
