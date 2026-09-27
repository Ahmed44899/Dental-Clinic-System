from importlib import import_module
from io import StringIO
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.core.management import call_command, CommandError
from django.db import connection, IntegrityError, transaction
from django.utils import timezone

from clinics.ownership import audit_ownership, BUSINESS_MODELS, RELATIONS
from clinics.test_isolation import world, png


pytestmark = pytest.mark.django_db
catch_up = import_module('clinics.migrations.0003_audit_ownership').catch_up_and_audit


@pytest.mark.parametrize('app,name', BUSINESS_MODELS)
def test_database_rejects_missing_clinic(world, app, name):
    model = apps.get_model(app, name)
    with pytest.raises(IntegrityError), transaction.atomic():
        model.objects.filter(pk=model.objects.first().pk).update(clinic_id=None)


@pytest.mark.parametrize('app,name,relation', RELATIONS)
def test_audit_detects_related_clinic_mismatch(world, app, name, relation):
    model = apps.get_model(app, name)
    record = model.objects.filter(clinic=world['clinics'][0]).first()
    model.objects.filter(pk=record.pk).update(clinic=world['clinics'][1])
    assert f'{app}.{name}.{relation}_clinic_mismatch' in {
        issue['code'] for issue in audit_ownership(apps)
    }
    with pytest.raises(CommandError):
        call_command('audit_clinic_ownership', stdout=StringIO())


def test_clean_audit_preserves_deactivated_membership_history(world):
    world['dentists'][0].clinic_memberships.update(is_active=False, role='admin')
    assert audit_ownership(apps) == []
    output = StringIO()
    call_command('audit_clinic_ownership', stdout=output)
    assert '"ok": true' in output.getvalue()


def test_audit_detects_missing_dentist_membership(world):
    world['dentists'][0].clinic_memberships.all().delete()
    assert 'appointments.Appointment.dentist_missing_membership' in {
        issue['code'] for issue in audit_ownership(apps)
    }


def test_audit_detects_xray_patient_mismatch_in_same_clinic(world):
    Patient = apps.get_model('patients', 'PatientProfile')
    patient = Patient.objects.create(clinic=world['clinics'][0], full_name='Other')
    image = world['images'][0]
    image.patient = patient
    image.save()
    assert 'xrays.XRay.appointment_patient_mismatch' in {
        issue['code'] for issue in audit_ownership(apps)
    }


def test_appointment_cannot_leave_existing_xray_on_different_patient(world):
    Patient = apps.get_model('patients', 'PatientProfile')
    Appointment = apps.get_model('appointments', 'Appointment')
    appointment = world['appointments'][0]
    Appointment.objects.filter(pk=appointment.pk).update(status='scheduled')
    other = Patient.objects.create(clinic=world['clinics'][0], full_name='Other')
    response = world['client'].patch(
        f'/api/appointments/{appointment.pk}/', {'patient': other.pk}, format='json',
    )
    assert response.status_code == 400
    assert 'patient' in response.data
    appointment.refresh_from_db()
    assert appointment.patient_id == world['patients'][0].pk
    assert audit_ownership(apps) == []


def test_xray_upload_rechecks_patient_after_validation(world):
    from unittest.mock import patch
    from xrays.serializers import XRaySerializer
    Appointment = apps.get_model('appointments', 'Appointment')
    Patient = apps.get_model('patients', 'PatientProfile')
    other = Patient.objects.create(clinic=world['clinics'][0], full_name='Other')
    appointment = world['appointments'][0]
    original_validate = XRaySerializer.validate

    def change_after_validation(serializer, data):
        result = original_validate(serializer, data)
        Appointment.objects.filter(pk=appointment.pk).update(patient=other)
        return result

    before = apps.get_model('xrays', 'XRay').objects.count()
    with patch.object(XRaySerializer, 'validate', change_after_validation):
        response = world['client'].post('/api/xrays/', {
            'patient': world['patients'][0].pk, 'appointment': appointment.pk,
            'image_file': png(),
        }, format='multipart')
    assert response.status_code == 400
    assert apps.get_model('xrays', 'XRay').objects.count() == before


def test_catch_up_assigns_only_single_legacy_clinic(nullable_apps):
    Clinic = nullable_apps.get_model('clinics', 'Clinic')
    clinic, _ = Clinic.objects.get_or_create(slug='dentomanager-existing', defaults={'name': 'Legacy'})
    Patient = nullable_apps.get_model('patients', 'PatientProfile')
    patient = Patient.objects.create(full_name='Unassigned')
    assert audit_ownership(nullable_apps)[0]['code'] == 'patients.PatientProfile.missing_clinic'
    catch_up(nullable_apps, SimpleNamespace(connection=connection))
    patient.refresh_from_db()
    assert patient.clinic_id == clinic.pk
    assert audit_ownership(nullable_apps) == []


def test_catch_up_refuses_ambiguous_ownership(nullable_apps):
    Clinic = nullable_apps.get_model('clinics', 'Clinic')
    Clinic.objects.create(slug='second', name='Second')
    Patient = nullable_apps.get_model('patients', 'PatientProfile')
    patient = Patient.objects.create(full_name='Unassigned')
    with pytest.raises(RuntimeError, match='single legacy clinic'):
        catch_up(nullable_apps, SimpleNamespace(connection=connection))
    patient.refresh_from_db()
    assert patient.clinic_id is None


def test_failed_audit_rolls_back_catch_up(nullable_apps):
    Clinic = nullable_apps.get_model('clinics', 'Clinic')
    clinic, _ = Clinic.objects.get_or_create(slug='dentomanager-existing', defaults={'name': 'Legacy'})
    Patient = nullable_apps.get_model('patients', 'PatientProfile')
    User = nullable_apps.get_model('accounts', 'CustomUser')
    Appointment = nullable_apps.get_model('appointments', 'Appointment')
    patient = Patient.objects.create(full_name='Unassigned')
    dentist = User.objects.create(username='without-membership')
    Appointment.objects.create(patient=patient, dentist=dentist, date_time=timezone.now())
    with pytest.raises(RuntimeError, match='dentist_missing_membership'), transaction.atomic():
        catch_up(nullable_apps, SimpleNamespace(connection=connection))
    patient.refresh_from_db()
    assert patient.clinic_id is None
