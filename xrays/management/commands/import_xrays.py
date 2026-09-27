import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DataError, IntegrityError, transaction

from clinics.models import Clinic
from patients.models import PatientProfile
from xrays.models import XRay


class Command(BaseCommand):
    help = 'Import X-rays into one explicitly selected clinic'

    def add_arguments(self, parser):
        parser.add_argument('--clinic', type=int, required=True)
        parser.add_argument('--source', default='xray_data.json')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        try:
            clinic = Clinic.objects.get(pk=options['clinic'], is_active=True)
        except Clinic.DoesNotExist as exc:
            raise CommandError('Select an active clinic.') from exc
        source = Path(options['source'])
        if not source.is_file():
            self.stdout.write(self.style.ERROR('Source file not found.'))
            return
        try:
            with source.open(encoding='utf-8') as stream:
                records = json.load(stream)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CommandError('Source must be a readable UTF-8 JSON file.') from exc
        if not isinstance(records, list):
            raise CommandError('Source JSON must be an array of records.')
        counts = dict(imported=0, skipped=0, errors=0)
        seen = set()
        for index, record in enumerate(records, start=1):
            try:
                # Catch outside atomic: a bad database write must roll back its
                # savepoint before the next record can query the database.
                with transaction.atomic():
                    outcome = self.import_record(record, clinic, options['dry_run'], seen)
            except (ValidationError, ValueError, TypeError, OverflowError, DataError, IntegrityError):
                counts['errors'] += 1
                # Do not log patient names, image URLs or raw database exceptions.
                self.stderr.write(f'Record {index}: invalid record; skipped.')
            else:
                counts[outcome] += 1
        self.stdout.write(
            f"Imported: {counts['imported']} | Skipped: {counts['skipped']} | Errors: {counts['errors']}"
        )
        if options['dry_run']:
            self.stdout.write('DRY RUN - nothing was saved.')

    def import_record(self, record, clinic, dry_run, seen):
        if not isinstance(record, dict):
            raise ValueError('A record must be an object.')
        patients = PatientProfile.objects.filter(clinic=clinic)
        patient_id = record.get('patient_id')
        if patient_id is not None:
            if isinstance(patient_id, bool) or not isinstance(patient_id, (int, str)):
                raise ValueError('Invalid patient ID.')
            value = str(patient_id)
            if not value.isascii() or not value.isdecimal() or len(value) > 19:
                raise ValueError('Invalid patient ID.')
            patient_id = int(value)
            if not 0 < patient_id <= 9223372036854775807:
                raise ValueError('Invalid patient ID.')
            patients = patients.filter(pk=patient_id)
        else:
            name = record.get('patient_name', '')
            if not isinstance(name, str) or not name.strip():
                raise ValueError('A patient identifier is required.')
            patients = patients.filter(full_name__iexact=name.strip())
        candidates = list(patients[:2])
        if len(candidates) != 1:
            raise ValueError('Patient must match exactly once within the selected clinic.')
        patient = candidates[0]
        external_id = record.get('xray_id')
        if isinstance(external_id, bool) or not isinstance(external_id, (str, int)):
            raise ValueError('Invalid external ID.')
        external_id = str(external_id).strip()
        if not external_id or len(external_id) > 100:
            raise ValueError('Invalid external ID.')
        key = (patient.pk, external_id)
        if key in seen or XRay.objects.filter(
            clinic=clinic, patient=patient, external_id=external_id,
        ).exists():
            return 'skipped'
        image_url = record.get('image_url', '')
        description = record.get('description', '')
        taken_at = record.get('taken_at')
        if not isinstance(image_url, str) or not isinstance(description, str):
            raise ValueError('Invalid text field.')
        if taken_at is not None and not isinstance(taken_at, str):
            raise ValueError('Invalid timestamp.')
        xray = XRay(
            clinic=clinic, patient=patient, external_id=external_id,
            image_cloud=image_url, storage_type='cloud', source='auto',
            taken_at=taken_at, description=description,
        )
        # Validate in dry-run too, including timestamp parsing and field lengths.
        xray.full_clean()
        if not dry_run:
            xray.save()
        seen.add(key)
        return 'imported'
