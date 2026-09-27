import json
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command, CommandError
from django.db import connection, OperationalError
from patients.factories import PatientProfileFactory
from xrays.models import XRay

pytestmark = pytest.mark.django_db


def run_import(tmp_path, patient, records, dry_run=False):
    source = tmp_path / 'import.json'
    source.write_text(json.dumps(records), encoding='utf-8')
    output, errors = StringIO(), StringIO()
    call_command('import_xrays', clinic=patient.clinic_id, source=str(source),
                 dry_run=dry_run, stdout=output, stderr=errors)
    return output.getvalue(), errors.getvalue()


def valid(patient, external_id='good'):
    return dict(patient_id=patient.pk, xray_id=external_id,
                image_url='https://example.com/scan.jpg', taken_at='2026-01-01T12:00:00Z')


@pytest.mark.parametrize('bad', [
    None, 'text', 123, [], True,
    {'patient_id': 'oops'}, {'patient_id': True}, {'patient_id': []},
    {'patient_id': 1.2}, {'patient_id': '9' * 50},
])
def test_bad_record_does_not_stop_later_records(tmp_path, bad):
    patient = PatientProfileFactory()
    output, _ = run_import(tmp_path, patient, [bad, valid(patient)])
    assert 'Imported: 1 | Skipped: 0 | Errors: 1' in output
    assert list(XRay.objects.values_list('external_id', flat=True)) == ['good']


@pytest.mark.parametrize('field,value', [
    ('taken_at', 'not-a-date'), ('taken_at', []),
    ('image_url', 'not-a-url'), ('description', None),
    ('xray_id', 'x' * 101), ('xray_id', {}), ('xray_id', True),
])
@pytest.mark.parametrize('dry_run', [False, True])
def test_field_validation_matches_dry_run(tmp_path, field, value, dry_run):
    patient = PatientProfileFactory()
    bad = valid(patient, 'bad')
    bad[field] = value
    output, _ = run_import(tmp_path, patient, [bad, valid(patient)], dry_run)
    assert 'Imported: 1 | Skipped: 0 | Errors: 1' in output
    assert XRay.objects.count() == (0 if dry_run else 1)


@pytest.mark.parametrize('dry_run', [False, True])
def test_duplicate_batch_records_have_consistent_counts(tmp_path, dry_run):
    patient = PatientProfileFactory()
    output, _ = run_import(tmp_path, patient, [valid(patient), valid(patient)], dry_run)
    assert 'Imported: 1 | Skipped: 1 | Errors: 0' in output
    assert XRay.objects.count() == (0 if dry_run else 1)


def test_database_record_failure_rolls_back_and_continues(tmp_path):
    patient = PatientProfileFactory()
    original = XRay.save

    def bad_write(instance, *args, **kwargs):
        if instance.external_id == 'bad':
            # Real NOT NULL violation poisons the transaction until its
            # savepoint is rolled back; the next row must still succeed.
            with connection.cursor() as cursor:
                cursor.execute('INSERT INTO xrays_xray (patient_id) VALUES (NULL)')
        return original(instance, *args, **kwargs)

    with patch.object(XRay, 'save', bad_write):
        output, _ = run_import(tmp_path, patient, [valid(patient, 'bad'), valid(patient)])
    assert 'Imported: 1 | Skipped: 0 | Errors: 1' in output
    assert XRay.objects.count() == 1


def test_database_outage_is_not_swallowed_as_invalid_input(tmp_path):
    patient = PatientProfileFactory()
    with patch.object(XRay, 'save', side_effect=OperationalError('offline')):
        with pytest.raises(OperationalError):
            run_import(tmp_path, patient, [valid(patient)])


@pytest.mark.parametrize('payload', ['{broken', '{}', 'null', '"text"'])
def test_invalid_source_structure_is_a_command_error(tmp_path, payload):
    patient = PatientProfileFactory()
    source = tmp_path / 'invalid.json'
    source.write_text(payload, encoding='utf-8')
    with pytest.raises(CommandError):
        call_command('import_xrays', clinic=patient.clinic_id, source=str(source))
    assert XRay.objects.count() == 0


def test_error_output_does_not_include_patient_or_image_details(tmp_path):
    patient = PatientProfileFactory(full_name='Synthetic Sensitive Name')
    bad = dict(patient_name=patient.full_name, xray_id='bad',
               image_url='https://example.com/private?token=synthetic', taken_at='invalid')
    _, errors = run_import(tmp_path, patient, [bad])
    assert 'Record 1' in errors
    assert patient.full_name not in errors
    assert 'token=' not in errors
