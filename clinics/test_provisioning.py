from io import StringIO
from unittest.mock import patch
import getpass

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.db import IntegrityError
from rest_framework.test import APIClient

from clinics.models import Clinic, ClinicMembership

pytestmark = pytest.mark.django_db
PASSWORD = 'Synthetic-only-frost!9247-lantern'
MODULE = 'clinics.management.commands.provision_clinic'


def invoke(**overrides):
    options = dict(name='Learning Clinic', slug='learning-clinic', username='new-owner',
                   email='owner@example.test', stdout=StringIO())
    options.update(overrides)
    call_command('provision_clinic', **options)
    return options['stdout'].getvalue()


@pytest.fixture
def prompts():
    with patch('builtins.input', return_value='learning-clinic') as confirm, patch(
        MODULE + '.getpass.getpass', return_value=PASSWORD,
    ) as password:
        yield confirm, password


def counts():
    return (Clinic.objects.count(), get_user_model().objects.count(), ClinicMembership.objects.count())


def test_provision_creates_only_local_admin_and_can_login(prompts):
    before = counts()
    output = invoke()
    assert counts() == tuple(value + 1 for value in before)
    clinic = Clinic.objects.get(slug='learning-clinic')
    user = get_user_model().objects.get(username='new-owner')
    membership = ClinicMembership.objects.get(clinic=clinic, user=user)
    assert user.check_password(PASSWORD)
    assert user.password != PASSWORD
    assert PASSWORD not in output
    assert user.is_active and not user.is_staff and not user.is_superuser
    assert membership.role == 'admin' and membership.is_active
    client = APIClient()
    response = client.post('/api/accounts/login/', dict(username=user.username, password=PASSWORD))
    assert response.status_code == 200
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'],
                       HTTP_X_CLINIC_ID=str(clinic.pk))
    assert client.get('/api/accounts/me/').data['role'] == 'admin'
    assert client.get('/api/patients/').data == []


@pytest.mark.parametrize('field,value', [
    ('name', ''), ('name', 'n' * 161), ('slug', 'bad slug'),
    ('slug', 's' * 101), ('username', 'bad user'),
    ('username', 'u' * 151), ('email', 'not-an-email'),
])
def test_invalid_fields_make_no_writes(prompts, field, value):
    before = counts()
    with pytest.raises(CommandError):
        invoke(**{field: value})
    assert counts() == before
    prompts[1].assert_not_called()


@pytest.mark.parametrize('kind', ['slug', 'username'])
def test_existing_identity_is_never_reused(prompts, kind):
    if kind == 'slug':
        Clinic.objects.create(name='Existing', slug='LEARNING-CLINIC')
    else:
        get_user_model().objects.create_user(username='NEW-OWNER', password='unchanged')
    before = counts()
    with pytest.raises(CommandError, match='already exists'):
        invoke()
    assert counts() == before
    prompts[1].assert_not_called()


def test_retry_does_not_create_or_reset_anything(prompts):
    invoke()
    before = counts()
    encoded = get_user_model().objects.get(username='new-owner').password
    with pytest.raises(CommandError):
        invoke()
    assert counts() == before
    assert get_user_model().objects.get(username='new-owner').password == encoded


def test_declined_confirmation_makes_no_writes(prompts):
    prompts[0].return_value = 'wrong-clinic'
    before = counts()
    with pytest.raises(CommandError, match='Confirmation'):
        invoke()
    assert counts() == before
    prompts[1].assert_not_called()


@pytest.mark.parametrize('values', [('short', 'short'), (PASSWORD, 'different')])
def test_invalid_password_makes_no_writes(prompts, values):
    prompts[1].side_effect = values
    before = counts()
    with pytest.raises(CommandError):
        invoke()
    assert counts() == before


@pytest.mark.parametrize('error', [EOFError(), KeyboardInterrupt(), getpass.GetPassWarning()])
def test_interrupted_or_insecure_prompt_makes_no_writes(prompts, error):
    prompts[1].side_effect = error
    before = counts()
    with pytest.raises(CommandError, match='interactive'):
        invoke()
    assert counts() == before


def test_membership_failure_rolls_back_user_and_clinic(prompts):
    before = counts()
    with patch(MODULE + '.ClinicMembership.objects.create', side_effect=IntegrityError('test')):
        with pytest.raises(CommandError, match='rolled back'):
            invoke()
    assert counts() == before


def test_missing_phase4_migration_refuses_provisioning(prompts):
    with patch(MODULE + '.MigrationRecorder.applied_migrations', return_value=set()):
        with pytest.raises(CommandError, match='Phase 4'):
            invoke()
    prompts[0].assert_not_called()


@pytest.mark.parametrize('when', ['before', 'during'])
def test_audit_failure_prevents_provisioning(prompts, when):
    before = counts()
    results = [[{'code': 'test'}]] if when == 'before' else [[], [{'code': 'test'}]]
    with patch(MODULE + '.audit_ownership', side_effect=results):
        with pytest.raises(CommandError, match='[Oo]wnership'):
            invoke()
    assert counts() == before


def test_provisioned_admin_cannot_access_another_clinic(prompts):
    other = Clinic.objects.create(name='Other', slug='other')
    invoke()
    client = APIClient()
    client.force_authenticate(get_user_model().objects.get(username='new-owner'))
    client.credentials(HTTP_X_CLINIC_ID=str(other.pk))
    assert client.get('/api/patients/').status_code == 403
    assert not ClinicMembership.objects.filter(clinic=other, user__username='new-owner').exists()
