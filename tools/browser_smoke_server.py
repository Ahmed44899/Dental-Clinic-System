"""Disposable, synthetic two-clinic UI fixture. Never uses the application DB.

Run: docker compose run --rm -p 127.0.0.1:8001:8001 web python tools/browser_smoke_server.py
"""
import os
from pathlib import Path
import secrets
import sys
import tempfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DJANGO_SETTINGS_MODULE'] = 'dental_clinic.settings_local'


def main():
    import django
    from django.conf import settings

    with tempfile.TemporaryDirectory(prefix='clinic-browser-') as directory:
        settings.DATABASES = {'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': str(Path(directory) / 'synthetic.sqlite3'),
        }}
        settings.MEDIA_ROOT = Path(directory) / 'media'
        settings.XRAY_CLOUD_UPLOAD_ENABLED = False
        django.setup()

        from datetime import timedelta
        from django.contrib.auth import get_user_model
        from django.core.files.base import ContentFile
        from django.core.management import call_command
        from django.utils import timezone
        from io import BytesIO
        from PIL import Image
        from appointments.models import Appointment, InvoiceLineItem, PaymentTransaction
        from clinics.models import Clinic, ClinicMembership
        from patients.models import PatientProfile
        from xrays.models import XRay

        call_command('migrate', verbosity=0)
        password = secrets.token_urlsafe(18)
        user = get_user_model().objects.create_user(username='browser-demo', password=password)
        for label, role, amount in [('A', 'admin', 100), ('B', 'receptionist', 900)]:
            clinic = Clinic.objects.create(name=f'Demo Clinic {label}', slug=f'browser-{label.lower()}')
            ClinicMembership.objects.create(clinic=clinic, user=user, role=role)
            dentist = get_user_model().objects.create_user(
                username=f'demo-dentist-{label.lower()}', first_name='Demo', last_name=label,
            )
            ClinicMembership.objects.create(clinic=clinic, user=dentist, role='dentist')
            patient = PatientProfile.objects.create(clinic=clinic, full_name=f'Fictional Patient {label}')
            visit = Appointment.objects.create(
                clinic=clinic, patient=patient, dentist=dentist,
                date_time=timezone.now() - timedelta(hours=1), status='completed',
            )
            InvoiceLineItem.objects.create(
                clinic=clinic, invoice=visit.invoice, description=f'Demo treatment {label}', unit_price=amount,
            )
            PaymentTransaction.objects.create(
                clinic=clinic, invoice=visit.invoice, transaction_type='payment',
                amount=amount, payment_method='cash', occurred_at=timezone.now(),
            )
            Appointment.objects.create(
                clinic=clinic, patient=patient, dentist=dentist,
                date_time=timezone.now() + timedelta(days=1),
            )
            image = BytesIO()
            Image.new('RGB', (100, 100), color='navy' if label == 'A' else 'teal').save(image, format='PNG')
            XRay.objects.create(
                clinic=clinic, patient=patient, appointment=visit,
                image_local=ContentFile(image.getvalue(), name=f'demo-{label}.png'),
                description=f'Synthetic image {label}', taken_at=timezone.now(),
            )
        call_command('audit_clinic_ownership')
        print(f'\nSynthetic UI: http://localhost:8001\nUsername: browser-demo\nPassword: {password}\n', flush=True)
        call_command('runserver', '0.0.0.0:8001', use_reloader=False)


if __name__ == '__main__':
    main()
