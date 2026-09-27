from django.db import migrations

from clinics.ownership import BUSINESS_MODELS, audit_ownership


def catch_up_and_audit(apps, schema_editor):
    alias = schema_editor.connection.alias
    models = [apps.get_model(app, name) for app, name in BUSINESS_MODELS]
    if any(model.objects.using(alias).filter(clinic_id__isnull=True).exists() for model in models):
        clinics = apps.get_model('clinics', 'Clinic').objects.using(alias)
        legacy = clinics.filter(slug='dentomanager-existing').first()
        if legacy is None or clinics.exclude(pk=legacy.pk).exists():
            raise RuntimeError('Cannot catch up unassigned records outside the single legacy clinic. Review ownership manually.')
        for model in models:
            model.objects.using(alias).filter(clinic_id__isnull=True).update(clinic_id=legacy.pk)
    issues = audit_ownership(apps, alias)
    if issues:
        raise RuntimeError(f'Clinic ownership audit failed: {issues}')


class Migration(migrations.Migration):
    dependencies = [('clinics', '0002_assign_existing_clinic')]
    operations = [migrations.RunPython(catch_up_and_audit, migrations.RunPython.noop)]
