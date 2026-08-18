from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('xrays', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='xray',
            name='cloud_public_id',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
