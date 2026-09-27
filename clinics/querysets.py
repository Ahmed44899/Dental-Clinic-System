"""Clinic-scoped prefetches for response metadata, never authorization."""
from django.db.models import Prefetch

from .models import ClinicMembership


def membership_cache_attr(clinic_id):
    # A prefetched user reused with another clinic must not reuse the first
    # clinic's roles, including an empty cached list.
    return f'_response_memberships_for_clinic_{clinic_id}'


def membership_prefetch(clinic, lookup='clinic_memberships'):
    return Prefetch(
        lookup,
        queryset=ClinicMembership.objects.filter(clinic_id=clinic.pk),
        to_attr=membership_cache_attr(clinic.pk),
    )
