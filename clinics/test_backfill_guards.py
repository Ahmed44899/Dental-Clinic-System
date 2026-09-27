from importlib import import_module
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.db import connection, transaction

from clinics.models import Clinic, ClinicMembership


pytestmark = pytest.mark.django_db
backfill = import_module('clinics.migrations.0002_assign_existing_clinic')


def test_backfill_refuses_other_clinics_without_assigning_records(nullable_apps):
    apps = nullable_apps
    Clinic = apps.get_model('clinics', 'Clinic')
    PatientProfile = apps.get_model('patients', 'PatientProfile')
    Clinic.objects.create(name='Another clinic', slug='another-clinic')
    patient = PatientProfile.objects.create(full_name='Unassigned')
    before = ClinicMembership.objects.count()
    with pytest.raises(RuntimeError, match='single-clinic'), transaction.atomic():
        backfill.assign_existing_clinic(apps, SimpleNamespace(connection=connection))
    patient.refresh_from_db()
    assert patient.clinic_id is None
    assert ClinicMembership.objects.count() == before


def test_backfill_refuses_unknown_roles_before_assigning_records(nullable_apps):
    apps = nullable_apps
    PatientProfile = apps.get_model('patients', 'PatientProfile')
    get_user_model().objects.create_user(username='unknown', role='unknown')
    patient = PatientProfile.objects.create(full_name='Unassigned')
    before = ClinicMembership.objects.count()
    with pytest.raises(RuntimeError, match='unsupported'), transaction.atomic():
        backfill.assign_existing_clinic(apps, SimpleNamespace(connection=connection))
    patient.refresh_from_db()
    assert patient.clinic_id is None
    assert ClinicMembership.objects.count() == before
