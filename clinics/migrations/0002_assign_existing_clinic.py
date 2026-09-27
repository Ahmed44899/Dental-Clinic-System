from django.db import migrations


BUSINESS_MODELS = [
    ('patients', 'PatientProfile'),
    ('appointments', 'Appointment'),
    ('appointments', 'Invoice'),
    ('appointments', 'InvoiceLineItem'),
    ('appointments', 'PaymentTransaction'),
    ('xrays', 'XRay'),
]
LEGACY_SLUG = 'dentomanager-existing'


def assign_existing_clinic(apps, schema_editor):
    # Historical models and the migration connection keep this reproducible.
    alias = schema_editor.connection.alias
    Clinic = apps.get_model('clinics', 'Clinic')
    Membership = apps.get_model('clinics', 'ClinicMembership')
    User = apps.get_model('accounts', 'CustomUser')
    clinics = Clinic.objects.using(alias)
    users = User.objects.using(alias)
    if clinics.exclude(slug=LEGACY_SLUG).exists():
        raise RuntimeError(
            'Existing-clinic backfill requires a single-clinic database. '
            'Review existing clinics before migrating.'
        )
    if users.filter(is_staff=False, is_superuser=False).exclude(
        role__in=['admin', 'dentist', 'receptionist'],
    ).exists():
        raise RuntimeError('Review unsupported legacy user roles before migrating.')

    clinic, _ = clinics.get_or_create(
        slug=LEGACY_SLUG, defaults={'name': 'DentoManager Clinic'},
    )
    for user in users.iterator():
        # Preserve effective legacy privileges only within the existing clinic.
        role = 'admin' if user.is_staff or user.is_superuser else user.role
        Membership.objects.using(alias).get_or_create(
            clinic_id=clinic.pk, user_id=user.pk,
            defaults={'role': role, 'is_active': user.is_active},
        )
    for app_label, model_name in BUSINESS_MODELS:
        model = apps.get_model(app_label, model_name)
        model.objects.using(alias).filter(clinic_id__isnull=True).update(
            clinic_id=clinic.pk,
        )


class Migration(migrations.Migration):
    dependencies = [
        ('clinics', '0001_initial'),
        ('patients', '0002_patientprofile_clinic'),
        ('appointments', '0004_appointment_clinic_invoice_clinic_and_more'),
        ('xrays', '0003_xray_clinic'),
    ]
    operations = [
        # Reverting the migration marker retains ownership and membership data.
        # Automatically deleting them could erase edits made after deployment.
        migrations.RunPython(assign_existing_clinic, migrations.RunPython.noop),
    ]
