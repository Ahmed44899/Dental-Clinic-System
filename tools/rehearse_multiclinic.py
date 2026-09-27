"""Synthetic PostgreSQL upgrade rehearsal; only for rehearsal.compose.yml."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PASSWORD = 'Synthetic-only-frost!9247-lantern'
MODELS = (
    ('accounts', 'CustomUser'), ('patients', 'PatientProfile'),
    ('appointments', 'Appointment'), ('appointments', 'Invoice'),
    ('appointments', 'InvoiceLineItem'), ('appointments', 'PaymentTransaction'),
    ('xrays', 'XRay'),
)
LEGACY = [
    ('patients', '0001_initial'),
    ('appointments', '0003_financial_ledger'),
    ('xrays', '0002_xray_cloud_public_id'),
]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def setup():
    require(os.environ.get('CLINIC_REHEARSAL') == 'synthetic-only',
            'Run only in the isolated rehearsal Compose project.')
    require(os.environ.get('DJANGO_SETTINGS_MODULE') == 'dental_clinic.settings_pytest',
            'Unexpected settings module.')
    from django.conf import settings
    db = settings.DATABASES['default']
    require(db['ENGINE'] == 'django.db.backends.postgresql'
            and db['HOST'] == 'rehearsal-db'
            and db['USER'] == 'rehearsal'
            and db['NAME'] in {'clinic_rehearsal', 'clinic_rehearsal_restore'},
            'Refusing a database outside the fixed rehearsal allowlist.')
    require(not settings.XRAY_CLOUD_UPLOAD_ENABLED, 'Cloud uploads must be disabled.')
    import django
    django.setup()
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database(), current_user')
        require(cursor.fetchone() == (db['NAME'], 'rehearsal'), 'Database identity mismatch.')
    print('Synthetic target:', db['HOST'], db['NAME'], flush=True)


def encode(value):
    from django.core.serializers.json import DjangoJSONEncoder
    return json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True)


def snapshot(registry, expected=None):
    result = {}
    for app, name in MODELS:
        model = registry.get_model(app, name)
        key = f'{app}.{name}'
        fields = expected[key]['fields'] if expected else [
            field.attname for field in model._meta.concrete_fields
        ]
        result[key] = dict(fields=fields, rows=list(model.objects.order_by('pk').values(*fields)))
    return json.loads(encode(result))


def saved_snapshot():
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute('SELECT payload FROM rehearsal_evidence WHERE id = 1')
        payload = cursor.fetchone()[0]
        return json.loads(payload) if isinstance(payload, str) else payload


def legacy_registry():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    executor = MigrationExecutor(connection)
    other = [target for target in executor.loader.graph.leaf_nodes()
             if target[0] not in {'clinics', 'patients', 'appointments', 'xrays'}]
    return executor, other + LEGACY


def seed():
    from django.contrib.auth.hashers import make_password
    from django.db import connection
    from django.utils import timezone
    require(not connection.introspection.table_names(), 'Seed requires a completely empty database.')
    executor, targets = legacy_registry()
    executor.migrate(targets)
    old = executor.loader.project_state(targets).apps
    User = old.get_model('accounts', 'CustomUser')
    admin = User.objects.create(username='legacy-owner', role='admin', password=make_password(PASSWORD))
    dentist = User.objects.create(username='legacy-dentist', role='dentist')
    patient = old.get_model('patients', 'PatientProfile').objects.create(
        full_name='Synthetic Legacy Patient', medical_notes='Synthetic preservation marker',
    )
    visit = old.get_model('appointments', 'Appointment').objects.create(
        patient=patient, dentist=dentist, created_by=admin,
        date_time=timezone.now(), status='completed',
    )
    invoice = old.get_model('appointments', 'Invoice').objects.create(
        appointment=visit, currency='EGP', notes='Synthetic ledger marker',
    )
    old.get_model('appointments', 'InvoiceLineItem').objects.create(
        invoice=invoice, description='Synthetic treatment', quantity=2, unit_price=125,
    )
    old.get_model('appointments', 'PaymentTransaction').objects.create(
        invoice=invoice, transaction_type='payment', amount=50,
        payment_method='cash', occurred_at=timezone.now(), recorded_by=admin,
    )
    old.get_model('xrays', 'XRay').objects.create(
        patient=patient, appointment=visit, cloud_public_id='synthetic/no-real-file',
        storage_type='cloud', description='Reference only; no cloud request',
    )
    data = snapshot(old)
    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE rehearsal_evidence (id integer PRIMARY KEY, payload jsonb NOT NULL)')
        cursor.execute('INSERT INTO rehearsal_evidence VALUES (1, %s::jsonb)', [encode(data)])
    print('PASS: seeded legacy schema and recorded every original field.', flush=True)


def verify_legacy():
    from django.db import connection
    from django.db.migrations.recorder import MigrationRecorder
    executor, targets = legacy_registry()
    require(not any(app == 'clinics' for app, name in
                    MigrationRecorder(connection).applied_migrations()), 'Restore is not the legacy state.')
    expected = saved_snapshot()
    require(snapshot(executor.loader.project_state(targets).apps, expected) == expected,
            'Restored legacy records differ from baseline.')
    print('PASS: restored backup matches all original fields and legacy migration state.', flush=True)


def upgrade():
    from django.apps import apps
    from django.core.management import call_command
    expected = saved_snapshot()
    call_command('migrate', interactive=False, verbosity=0)
    require(snapshot(apps, expected) == expected, 'Migration changed original data.')
    call_command('audit_clinic_ownership')
    from clinics.models import Clinic, ClinicMembership
    clinic = Clinic.objects.get(slug='dentomanager-existing')
    for app, name in MODELS[1:]:
        require(not apps.get_model(app, name).objects.exclude(clinic=clinic).exists(),
                f'{app}.{name} has incorrect ownership.')
    require(ClinicMembership.objects.filter(clinic=clinic).count() == 2, 'Legacy memberships missing.')
    print('PASS: migration preserved all original values and assigned ownership.', flush=True)


def verify():
    from decimal import Decimal
    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    from rest_framework.test import APIClient
    from clinics.models import Clinic, ClinicMembership
    from patients.models import PatientProfile
    from appointments.models import Invoice

    legacy = Clinic.objects.get(slug='dentomanager-existing')
    new = Clinic.objects.get(slug='rehearsal-second')
    User = get_user_model()
    owner = User.objects.get(username='rehearsal-owner')
    require(not owner.is_staff and not owner.is_superuser, 'Unexpected platform privilege.')
    require(ClinicMembership.objects.get(clinic=new, user=owner).role == 'admin',
            'Missing clinic admin role.')
    clients = []
    for username, clinic in [('legacy-owner', legacy), ('rehearsal-owner', new)]:
        client = APIClient()
        login = client.post('/api/accounts/login/', {'username': username, 'password': PASSWORD})
        require(login.status_code == 200, f'{username} cannot log in.')
        client.credentials(HTTP_AUTHORIZATION='Bearer ' + login.data['access'],
                           HTTP_X_CLINIC_ID=str(clinic.pk))
        clients.append(client)
    old_client, new_client = clients
    existing = PatientProfile.objects.get(full_name='Synthetic Legacy Patient')
    require(new_client.get('/api/patients/').data == [], 'New clinic sees legacy patients.')
    created = new_client.post('/api/patients/', {
        'full_name': 'Synthetic Second Patient', 'clinic': legacy.pk,
    }, format='json')
    require(created.status_code == 201, 'New clinic patient creation failed.')
    other = PatientProfile.objects.get(pk=created.data['id'])
    require(other.clinic_id == new.pk, 'Client-supplied ownership was accepted.')
    for client, own, foreign in [(old_client, existing, other), (new_client, other, existing)]:
        response = client.get('/api/patients/')
        require(response.status_code == 200 and [r['id'] for r in response.data] == [own.pk],
                'Patient list isolation failed.')
        require(client.get(f'/api/patients/{foreign.pk}/').status_code == 404,
                'Foreign patient detail visible.')
    old_invoice = Invoice.objects.get(appointment__patient=existing)
    require(old_invoice.currency == 'EGP' and old_invoice.total == Decimal('250')
            and old_invoice.net_paid == Decimal('50') and old_invoice.balance == Decimal('200'),
            'Legacy financial values changed.')
    require(new_client.get('/api/appointments/').data == [], 'Legacy appointments exposed.')
    require(new_client.get('/api/xrays/').data == [], 'Legacy X-rays exposed.')
    require(new_client.get(
        f'/api/appointments/{old_invoice.appointment_id}/invoice/'
    ).status_code == 404, 'Legacy invoice exposed.')
    call_command('audit_clinic_ownership')
    print('PASS: real JWT logins, patient creation, bidirectional isolation, ledger preservation, clean audit.',
          flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['seed', 'upgrade', 'verify', 'verify-legacy'])
    args = parser.parse_args()
    setup()
    {'seed': seed, 'upgrade': upgrade, 'verify': verify, 'verify-legacy': verify_legacy}[args.stage]()
