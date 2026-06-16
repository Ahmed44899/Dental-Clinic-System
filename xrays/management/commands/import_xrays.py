from django.core.management.base import BaseCommand
from django.utils import timezone
from xrays.models import XRay
from patients.models import PatientProfile
import json
import os


class Command(BaseCommand):
    help = 'Import xrays from external database into patient profiles'

    def add_arguments(self, parser):
        """Lets you pass options: python manage.py import_xrays --source /path/to/data.json"""
        parser.add_argument('--source', type=str, default='xray_data.json',
                            help='Path to the xray data file')
        parser.add_argument('--dry-run', action='store_true',
                            help='Preview what would be imported without saving anything')

    def handle(self, *args, **options):
        source_file = options['source']
        dry_run = options['dry_run']

        if not os.path.exists(source_file):
            self.stdout.write(self.style.ERROR(f'File not found: {source_file}'))
            return

        with open(source_file, 'r') as f:
            xray_data = json.load(f)

        imported = 0
        skipped = 0
        errors = 0

        for record in xray_data:
            try:
                # Match patient by name or external ID
                patient = PatientProfile.objects.filter(
                    full_name__icontains=record.get('patient_name', '')
                ).first()

                if not patient:
                    self.stdout.write(
                        self.style.WARNING(f"Patient not found: {record.get('patient_name')}")
                    )
                    errors += 1
                    continue

                # Skip if already imported (unique_together protects against duplicates)
                if XRay.objects.filter(patient=patient, external_id=record.get('xray_id')).exists():
                    skipped += 1
                    continue

                if not dry_run:
                    XRay.objects.create(
                        patient=patient,
                        external_id=record.get('xray_id', ''),
                        image_cloud=record.get('image_url', ''),
                        storage_type='cloud',
                        source='auto',
                        taken_at=record.get('taken_at'),
                        description=record.get('description', ''),
                    )

                imported += 1
                self.stdout.write(f"  Imported xray for {patient.full_name}")

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error: {e}'))
                errors += 1

        # Final summary
        self.stdout.write(self.style.SUCCESS(
            f'\nDone — Imported: {imported} | Skipped: {skipped} | Errors: {errors}'
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — nothing was saved.'))