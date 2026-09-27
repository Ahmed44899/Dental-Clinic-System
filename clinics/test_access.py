import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework.exceptions import PermissionDenied

from clinics.access import resolve_membership
from clinics.models import Clinic, ClinicMembership


pytestmark = pytest.mark.django_db


@pytest.fixture
def membership():
    user = get_user_model().objects.create_user(username='member', role='admin')
    clinic = Clinic.objects.create(name='First', slug='first')
    return ClinicMembership.objects.create(user=user, clinic=clinic, role='dentist')


def test_single_membership_uses_clinic_role(membership):
    result = resolve_membership(membership.user)
    assert result.pk == membership.pk
    assert result.role == 'dentist'  # Global user.role must not grant admin access.


def test_multiple_memberships_require_selection(membership):
    second = Clinic.objects.create(name='Second', slug='second')
    other = ClinicMembership.objects.create(
        user=membership.user, clinic=second, role='admin',
    )
    with pytest.raises(PermissionDenied):
        resolve_membership(membership.user)
    assert resolve_membership(membership.user, str(second.pk)).pk == other.pk


def test_another_clinic_is_denied_even_for_superuser(membership):
    membership.user.is_superuser = True
    membership.user.is_staff = True
    membership.user.save()
    second = Clinic.objects.create(name='Second', slug='second')
    with pytest.raises(PermissionDenied):
        resolve_membership(membership.user, second.pk)


@pytest.mark.parametrize('target', ['membership', 'clinic', 'user'])
def test_revocation_is_checked_on_every_lookup(membership, target):
    user = membership.user
    assert resolve_membership(user).pk == membership.pk
    obj = {'membership': membership, 'clinic': membership.clinic, 'user': user}[target]
    type(obj).objects.filter(pk=obj.pk).update(is_active=False)
    with pytest.raises(PermissionDenied):
        resolve_membership(user, membership.clinic_id)


@pytest.mark.parametrize('value', ['', 'abc', '-1', '0', True, '9' * 5000])
def test_invalid_clinic_selection_is_denied(membership, value):
    with pytest.raises(PermissionDenied):
        resolve_membership(membership.user, value)


def test_anonymous_user_is_denied():
    with pytest.raises(PermissionDenied):
        resolve_membership(AnonymousUser())


def test_user_without_memberships_is_denied():
    user = get_user_model().objects.create_user(username='outsider')
    with pytest.raises(PermissionDenied):
        resolve_membership(user)
