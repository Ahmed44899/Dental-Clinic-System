"""Version-one ownership audit; kept stable for the Phase 4 migration.

Accept an app registry so both historical migrations and operator commands use
the same checks. Reports contain counts and record IDs, never patient details.
"""
from django.db.models import Exists, F, OuterRef


BUSINESS_MODELS = (
    ('patients', 'PatientProfile'), ('appointments', 'Appointment'),
    ('appointments', 'Invoice'), ('appointments', 'InvoiceLineItem'),
    ('appointments', 'PaymentTransaction'), ('xrays', 'XRay'),
)
RELATIONS = (
    ('appointments', 'Appointment', 'patient'),
    ('appointments', 'Invoice', 'appointment'),
    ('appointments', 'InvoiceLineItem', 'invoice'),
    ('appointments', 'PaymentTransaction', 'invoice'),
    ('xrays', 'XRay', 'patient'), ('xrays', 'XRay', 'appointment'),
)


def audit_ownership(apps, alias='default'):
    issues = []

    def report(code, queryset):
        count = queryset.count()
        if count:
            issues.append(dict(
                code=code, count=count,
                sample_ids=list(queryset.order_by('pk').values_list('pk', flat=True)[:20]),
            ))

    for app, name in BUSINESS_MODELS:
        records = apps.get_model(app, name).objects.using(alias)
        report(f'{app}.{name}.missing_clinic', records.filter(clinic_id__isnull=True))
    for app, name, relation in RELATIONS:
        records = apps.get_model(app, name).objects.using(alias).filter(
            clinic_id__isnull=False, **{f'{relation}__clinic_id__isnull': False},
        ).exclude(clinic_id=F(f'{relation}__clinic_id'))
        report(f'{app}.{name}.{relation}_clinic_mismatch', records)
    XRay = apps.get_model('xrays', 'XRay')
    report('xrays.XRay.appointment_patient_mismatch', XRay.objects.using(alias).filter(
        appointment_id__isnull=False,
    ).exclude(patient_id=F('appointment__patient_id')))
    Membership = apps.get_model('clinics', 'ClinicMembership')
    # Historical attribution survives deactivation and role changes. Membership
    # existence matters here; current permission to book is checked by the API.
    appointments = apps.get_model('appointments', 'Appointment').objects.using(alias)
    memberships = Membership.objects.using(alias).filter(
        clinic_id=OuterRef('clinic_id'), user_id=OuterRef('dentist_id'),
    )
    report('appointments.Appointment.dentist_missing_membership', appointments.filter(
        clinic_id__isnull=False,
    ).annotate(has_membership=Exists(memberships)).filter(has_membership=False))
    return issues
