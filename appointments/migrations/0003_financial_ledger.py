from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def migrate_legacy_invoice_values(apps, schema_editor):
    Invoice = apps.get_model('appointments', 'Invoice')
    InvoiceLineItem = apps.get_model('appointments', 'InvoiceLineItem')
    PaymentTransaction = apps.get_model('appointments', 'PaymentTransaction')

    for invoice in Invoice.objects.select_related('appointment').iterator():
        if invoice.total_fees > Decimal('0.00'):
            InvoiceLineItem.objects.create(
                invoice=invoice,
                description='Migrated legacy invoice total',
                quantity=Decimal('1.00'),
                unit_price=invoice.total_fees,
                created_by_id=invoice.appointment.created_by_id,
            )
        if invoice.amount_paid > Decimal('0.00'):
            PaymentTransaction.objects.create(
                invoice=invoice,
                transaction_type='payment',
                amount=invoice.amount_paid,
                payment_method=invoice.payment_method,
                notes='Migrated from the legacy accumulated payment field.',
                occurred_at=invoice.payment_date or invoice.appointment.updated_at,
                recorded_by_id=invoice.appointment.created_by_id,
            )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('appointments', '0002_appointment_duration_and_constraints'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='currency',
            field=models.CharField(
                choices=[('USD', 'US Dollar'), ('EGP', 'Egyptian Pound')],
                default='USD',
                max_length=3,
            ),
        ),
        migrations.CreateModel(
            name='InvoiceLineItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.CharField(max_length=255)),
                ('procedure_code', models.CharField(blank=True, max_length=50)),
                ('quantity', models.DecimalField(decimal_places=2, default=1, max_digits=8)),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_invoice_items', to=settings.AUTH_USER_MODEL)),
                ('invoice', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='line_items', to='appointments.invoice')),
            ],
            options={'ordering': ['created_at', 'id']},
        ),
        migrations.CreateModel(
            name='PaymentTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transaction_type', models.CharField(choices=[('payment', 'Payment'), ('refund', 'Refund')], max_length=10)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('payment_method', models.CharField(choices=[('cash', 'Cash'), ('card', 'Card'), ('insurance', 'Insurance'), ('bank_transfer', 'Bank transfer'), ('other', 'Other')], max_length=20)),
                ('reference', models.CharField(blank=True, max_length=120)),
                ('notes', models.TextField(blank=True)),
                ('occurred_at', models.DateTimeField()),
                ('recorded_at', models.DateTimeField(auto_now_add=True)),
                ('invoice', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='appointments.invoice')),
                ('recorded_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='recorded_payment_transactions', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['occurred_at', 'id']},
        ),
        migrations.AddConstraint(
            model_name='invoicelineitem',
            constraint=models.CheckConstraint(check=models.Q(('quantity__gt', 0)), name='invoice_item_quantity_positive'),
        ),
        migrations.AddConstraint(
            model_name='invoicelineitem',
            constraint=models.CheckConstraint(check=models.Q(('unit_price__gte', 0)), name='invoice_item_price_nonnegative'),
        ),
        migrations.AddConstraint(
            model_name='paymenttransaction',
            constraint=models.CheckConstraint(check=models.Q(('amount__gt', 0)), name='payment_transaction_amount_positive'),
        ),
        migrations.RunPython(migrate_legacy_invoice_values, migrations.RunPython.noop),
        migrations.RemoveField(model_name='invoice', name='amount_paid'),
        migrations.RemoveField(model_name='invoice', name='payment_date'),
        migrations.RemoveField(model_name='invoice', name='payment_method'),
        migrations.RemoveField(model_name='invoice', name='status'),
        migrations.RemoveField(model_name='invoice', name='total_fees'),
    ]
