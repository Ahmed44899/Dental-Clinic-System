from django.db import migrations, models
from django.db.models import Count


def reject_existing_duplicate_slots(apps, schema_editor):
    Appointment = apps.get_model('appointments', 'Appointment')
    duplicate = (
        Appointment.objects.filter(status='scheduled')
        .values('dentist_id', 'date_time')
        .annotate(total=Count('id'))
        .filter(total__gt=1)
        .order_by('dentist_id', 'date_time')
        .first()
    )
    if duplicate:
        raise RuntimeError(
            'Cannot add appointment slot protection because scheduled '
            'appointments already share a dentist and start time. Resolve '
            'the duplicate appointments, then run migrate again.'
        )


class Migration(migrations.Migration):
    dependencies = [
        ('appointments', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='duration_minutes',
            field=models.PositiveSmallIntegerField(
                default=30,
                help_text='Planned chair time in minutes.',
            ),
        ),
        migrations.AddField(
            model_name='appointment',
            name='emergency_reason',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='appointment',
            name='is_emergency_overbook',
            field=models.BooleanField(default=False),
        ),
        migrations.AddConstraint(
            model_name='appointment',
            constraint=models.CheckConstraint(
                check=models.Q(
                    duration_minutes__gte=5,
                    duration_minutes__lte=480,
                ),
                name='appointment_duration_between_5_and_480',
            ),
        ),
        migrations.RunPython(
            reject_existing_duplicate_slots,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='appointment',
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    is_emergency_overbook=False,
                    status='scheduled',
                ),
                fields=('dentist', 'date_time'),
                name='unique_scheduled_dentist_start',
            ),
        ),
    ]
