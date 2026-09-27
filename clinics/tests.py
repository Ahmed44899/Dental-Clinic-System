from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from clinics.models import Clinic, ClinicMembership
from patients.models import PatientProfile


@pytest.mark.django_db
def test_user_can_hold_different_roles_in_two_clinics():
    user = get_user_model().objects.create_user(username='shared-dentist')
    first = Clinic.objects.create(name='First clinic', slug='first')
    second = Clinic.objects.create(name='Second clinic', slug='second')
    ClinicMembership.objects.create(clinic=first, user=user, role='admin')
    ClinicMembership.objects.create(clinic=second, user=user, role='dentist')

    assert set(user.clinic_memberships.values_list('role', flat=True)) == {
        'admin', 'dentist',
    }


@pytest.mark.django_db
def test_inactive_membership_cannot_be_duplicated():
    clinic = Clinic.objects.create(name='Clinic', slug='clinic')
    user = get_user_model().objects.create_user(username='member')
    ClinicMembership.objects.create(
        clinic=clinic, user=user, role='dentist', is_active=False,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        ClinicMembership.objects.create(clinic=clinic, user=user, role='admin')


@pytest.mark.django_db
def test_invalid_membership_role_is_rejected_by_database():
    clinic = Clinic.objects.create(name='Clinic', slug='clinic')
    user = get_user_model().objects.create_user(username='member')
    with pytest.raises(IntegrityError), transaction.atomic():
        ClinicMembership.objects.create(clinic=clinic, user=user, role='owner')


@pytest.mark.django_db
def test_clinic_slug_is_unique():
    Clinic.objects.create(name='First', slug='clinic')
    with pytest.raises(IntegrityError), transaction.atomic():
        Clinic.objects.create(name='Second', slug='clinic')


@pytest.mark.django_db
def test_clinic_with_patients_cannot_be_deleted():
    clinic = Clinic.objects.create(name='Clinic', slug='clinic')
    patient = PatientProfile.objects.create(clinic=clinic, full_name='Patient')
    with pytest.raises(ProtectedError):
        clinic.delete()
    assert PatientProfile.objects.get(pk=patient.pk).clinic_id == clinic.pk


@pytest.mark.django_db
def test_membership_protects_clinic_and_user_from_deletion():
    clinic = Clinic.objects.create(name='Clinic', slug='clinic')
    user = get_user_model().objects.create_user(username='member')
    ClinicMembership.objects.create(clinic=clinic, user=user, role='dentist')
    for obj in (clinic, user):
        with pytest.raises(ProtectedError):
            obj.delete()


@pytest.mark.django_db(transaction=True)
def test_additive_migrations_preserve_existing_records():
    # Use historical models: current models expect columns absent in the old schema.
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    phase_one = [
        ('clinics', '0001_initial'),
        ('patients', '0002_patientprofile_clinic'),
        ('appointments', '0004_appointment_clinic_invoice_clinic_and_more'),
        ('xrays', '0003_xray_clinic'),
    ]
    previous = [
        ('appointments', '0003_financial_ledger'),
        ('patients', '0001_initial'),
        ('xrays', '0002_xray_cloud_public_id'),
        ('clinics', None),
    ]
    try:
        executor.migrate(previous)
        old_apps = executor.loader.project_state(
            [target for target in previous if target[1] is not None]
        ).apps
        User = old_apps.get_model('accounts', 'CustomUser')
        Patient = old_apps.get_model('patients', 'PatientProfile')
        Appointment = old_apps.get_model('appointments', 'Appointment')
        Invoice = old_apps.get_model('appointments', 'Invoice')
        Item = old_apps.get_model('appointments', 'InvoiceLineItem')
        Payment = old_apps.get_model('appointments', 'PaymentTransaction')
        XRay = old_apps.get_model('xrays', 'XRay')
        user = User.objects.create(username='legacy-dentist', role='dentist')
        patient = Patient.objects.create(
            full_name='Legacy patient', medical_notes='Preserve this note',
        )
        appointment = Appointment.objects.create(
            patient=patient, dentist=user, date_time=timezone.now(),
        )
        invoice = Invoice.objects.create(appointment=appointment, currency='EGP')
        item = Item.objects.create(
            invoice=invoice, description='Treatment', quantity=2, unit_price=125,
        )
        payment = Payment.objects.create(
            invoice=invoice, transaction_type='payment', amount=50,
            payment_method='cash', occurred_at=timezone.now(),
        )
        xray = XRay.objects.create(
            patient=patient, appointment=appointment,
            cloud_public_id='legacy/private-image', storage_type='cloud',
        )
        expected = [
            ('patients', 'PatientProfile', patient.pk),
            ('appointments', 'Appointment', appointment.pk),
            ('appointments', 'Invoice', invoice.pk),
            ('appointments', 'InvoiceLineItem', item.pk),
            ('appointments', 'PaymentTransaction', payment.pk),
            ('xrays', 'XRay', xray.pk),
        ]

        executor = MigrationExecutor(connection)
        executor.migrate(phase_one)
        new_apps = executor.loader.project_state(phase_one).apps
        for app, name, pk in expected:
            model = new_apps.get_model(app, name)
            assert model.objects.count() == 1
            assert model.objects.get(pk=pk).clinic_id is None

        assert new_apps.get_model('clinics', 'Clinic').objects.count() == 0
        assert new_apps.get_model('clinics', 'ClinicMembership').objects.count() == 0
        assert new_apps.get_model('accounts', 'CustomUser').objects.get(
            pk=user.pk
        ).role == 'dentist'
        assert new_apps.get_model('patients', 'PatientProfile').objects.get(
            pk=patient.pk
        ).medical_notes == 'Preserve this note'
        migrated_appointment = new_apps.get_model(
            'appointments', 'Appointment',
        ).objects.get(pk=appointment.pk)
        assert migrated_appointment.patient_id == patient.pk
        assert migrated_appointment.dentist_id == user.pk
        migrated_invoice = new_apps.get_model(
            'appointments', 'Invoice',
        ).objects.get(pk=invoice.pk)
        assert migrated_invoice.appointment_id == appointment.pk
        assert migrated_invoice.currency == 'EGP'
        migrated_item = new_apps.get_model(
            'appointments', 'InvoiceLineItem',
        ).objects.get(pk=item.pk)
        assert migrated_item.invoice_id == invoice.pk
        assert migrated_item.quantity * migrated_item.unit_price == Decimal('250')
        migrated_payment = new_apps.get_model(
            'appointments', 'PaymentTransaction',
        ).objects.get(pk=payment.pk)
        assert migrated_payment.invoice_id == invoice.pk
        assert migrated_payment.amount == Decimal('50')
        migrated_xray = new_apps.get_model('xrays', 'XRay').objects.get(pk=xray.pk)
        assert migrated_xray.patient_id == patient.pk
        assert migrated_xray.appointment_id == appointment.pk
        assert migrated_xray.cloud_public_id == 'legacy/private-image'
        # Continue the same preserved dataset through the ownership backfill.
        User = new_apps.get_model('accounts', 'CustomUser')
        inactive = User.objects.create(
            username='inactive-reception', role='receptionist', is_active=False,
        )
        staff = User.objects.create(username='legacy-staff', is_staff=True)
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        final_apps = executor.loader.project_state(latest).apps
        clinic = final_apps.get_model('clinics', 'Clinic').objects.get(
            slug='dentomanager-existing',
        )
        for app, name, pk in expected:
            assert final_apps.get_model(app, name).objects.get(pk=pk).clinic_id == clinic.pk
        memberships = final_apps.get_model('clinics', 'ClinicMembership').objects
        assert memberships.get(user_id=user.pk).role == 'dentist'
        assert memberships.get(user_id=staff.pk).role == 'admin'
        assert memberships.get(user_id=inactive.pk).is_active is False
        assert memberships.get(user_id=inactive.pk).role == 'receptionist'
        # Retry must not overwrite an administrator's later membership edits.
        memberships.filter(user_id=user.pk).update(is_active=False)
        from importlib import import_module
        backfill = import_module('clinics.migrations.0002_assign_existing_clinic')
        with connection.schema_editor() as editor:
            backfill.assign_existing_clinic(final_apps, editor)
        assert memberships.count() == 3
        assert memberships.get(user_id=user.pk).is_active is False
        assert final_apps.get_model('appointments', 'PaymentTransaction').objects.get(
            pk=payment.pk
        ).amount == Decimal('50')
    finally:
        # Always restore the schema so subsequent tests can use current models.
        MigrationExecutor(connection).migrate(latest)
