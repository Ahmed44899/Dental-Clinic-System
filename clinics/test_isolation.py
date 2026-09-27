from datetime import timedelta
from decimal import Decimal
from io import BytesIO, StringIO
import json
from unittest.mock import patch

import pytest
from PIL import Image
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from clinics.models import Clinic, ClinicMembership
from patients.models import PatientProfile
from appointments.models import Appointment, InvoiceLineItem, PaymentTransaction
from xrays.models import XRay

pytestmark = pytest.mark.django_db


@pytest.fixture
def world():
    clinics, users, dentists, patients, appointments, images, items = [], [], [], [], [], [], []
    User = get_user_model()
    for label, amount in [('a', '100'), ('b', '900')]:
        clinic = Clinic.objects.create(name=label.upper(), slug='isolation-' + label)
        user = User.objects.create_user(username=label + '-admin', role='admin', is_staff=True)
        dentist = User.objects.create_user(username=label + '-dentist', role='dentist')
        for person, role in [(user, 'admin'), (dentist, 'dentist')]:
            ClinicMembership.objects.create(clinic=clinic, user=person, role=role)
        patient = PatientProfile.objects.create(clinic=clinic, full_name='Shared Name')
        appointment = Appointment.objects.create(
            clinic=clinic, patient=patient, dentist=dentist,
            date_time=timezone.now(), status='completed',
        )
        invoice = appointment.invoice
        item = InvoiceLineItem.objects.create(
            clinic=clinic, invoice=invoice, description='Treatment', unit_price=amount,
        )
        PaymentTransaction.objects.create(
            clinic=clinic, invoice=invoice, transaction_type='payment', amount=amount,
            payment_method='cash', occurred_at=timezone.now(), recorded_by=user,
        )
        image = XRay.objects.create(
            clinic=clinic, patient=patient, appointment=appointment,
            cloud_public_id='private/' + label, storage_type='cloud',
        )
        for collection, obj in [
            (clinics, clinic), (users, user), (dentists, dentist), (patients, patient),
            (appointments, appointment), (images, image), (items, item),
        ]:
            collection.append(obj)
    client = APIClient()
    client.force_authenticate(users[0])
    client.credentials(HTTP_X_CLINIC_ID=str(clinics[0].pk))
    return dict(
        clinics=clinics, users=users, dentists=dentists, patients=patients,
        appointments=appointments, images=images, items=items, client=client,
    )


def png():
    stream = BytesIO()
    Image.new('RGB', (8, 8)).save(stream, format='PNG')
    return SimpleUploadedFile('scan.png', stream.getvalue(), content_type='image/png')


def foreign_urls(w):
    visit, patient, image, item, user = (
        w['appointments'][1].pk, w['patients'][1].pk, w['images'][1].pk,
        w['items'][1].pk, w['users'][1].pk,
    )
    return [
        f'/api/patients/{patient}/',
        f'/api/appointments/{visit}/',
        f'/api/appointments/{visit}/invoice/',
        f'/api/appointments/{visit}/invoice/items/',
        f'/api/appointments/{visit}/invoice/items/{item}/',
        f'/api/appointments/{visit}/invoice/transactions/',
        f'/api/xrays/{image}/',
        f'/api/xrays/{image}/image/',
    ]


@pytest.mark.parametrize('index', range(8))
def test_foreign_detail_and_nested_routes_are_hidden(world, index):
    assert world['client'].get(foreign_urls(world)[index]).status_code == 404


@pytest.mark.parametrize('path,key', [
    ('/api/patients/', 'patients'),
    ('/api/patients/search/?q=Shared', 'patients'),
    ('/api/appointments/', 'appointments'),
    ('/api/xrays/', 'images'),
    ('/api/accounts/dentists/', 'dentists'),
])
def test_lists_and_searches_exclude_other_clinic(world, path, key):
    response = world['client'].get(path)
    assert response.status_code == 200
    assert [row['id'] for row in response.data] == [world[key][0].pk]


def test_staff_directory_excludes_other_clinic(world):
    response = world['client'].get('/api/accounts/staff/')
    assert {row['id'] for row in response.data} == {
        world['users'][0].pk, world['dentists'][0].pk,
    }


@pytest.mark.parametrize('local_active', [True, False])
def test_staff_directory_matches_one_local_membership(world, local_active):
    clinic, other = world['clinics']
    viewer, subject = world['users'][0], world['dentists'][0]
    ClinicMembership.objects.filter(clinic=clinic, user=viewer).update(role='receptionist')
    ClinicMembership.objects.create(clinic=other, user=subject, role='dentist')
    ClinicMembership.objects.filter(clinic=clinic, user=subject).update(is_active=local_active)
    response = world['client'].get('/api/accounts/staff/')
    assert response.status_code == 200
    ids = [row['id'] for row in response.data]
    assert ids.count(subject.pk) == (1 if local_active else 0)
    assert ids.count(viewer.pk) == 1


def test_report_and_dentist_filter_do_not_reveal_foreign_money(world):
    response = world['client'].get('/api/appointments/financial-reports/')
    assert response.status_code == 200
    assert response.data['summary']['revenue'] == '100.00'
    assert response.data['summary']['collections'] == '100.00'
    assert [d['id'] for d in response.data['dentists']] == [world['dentists'][0].pk]
    filtered = world['client'].get(
        '/api/appointments/financial-reports/', {'dentist': world['dentists'][1].pk},
    )
    assert filtered.status_code == 200
    assert filtered.data['summary']['revenue'] == '0.00'
    assert filtered.data['dentists'] == []


def test_patient_creation_assigns_server_clinic(world):
    response = world['client'].post('/api/patients/', {
        'full_name': 'New patient', 'clinic': world['clinics'][1].pk,
    })
    assert response.status_code == 201
    assert PatientProfile.objects.get(pk=response.data['id']).clinic_id == world['clinics'][0].pk


@pytest.mark.parametrize('foreign_field', ['patient', 'dentist'])
def test_booking_rejects_foreign_relations(world, foreign_field):
    data = {
        'patient': world['patients'][0].pk, 'dentist': world['dentists'][0].pk,
        'date_time': (timezone.now() + timedelta(days=1)).isoformat(),
    }
    data[foreign_field] = world['patients' if foreign_field == 'patient' else 'dentists'][1].pk
    assert world['client'].post('/api/appointments/', data).status_code == 400
    assert Appointment.objects.count() == 2


def test_booking_and_financial_writers_assign_clinic(world):
    clinic = world['clinics'][0]
    response = world['client'].post('/api/appointments/', {
        'patient': world['patients'][0].pk, 'dentist': world['dentists'][0].pk,
        'date_time': (timezone.now() + timedelta(days=1)).isoformat(),
    })
    assert response.status_code == 201
    visit = Appointment.objects.get(pk=response.data['id'])
    assert visit.clinic_id == visit.invoice.clinic_id == clinic.pk
    item = world['client'].post(f'/api/appointments/{visit.pk}/invoice/items/', {
        'description': 'Charge', 'quantity': '1', 'unit_price': '50',
    })
    assert item.status_code == 201
    assert InvoiceLineItem.objects.get(pk=item.data['id']).clinic_id == clinic.pk
    payment = world['client'].post(f'/api/appointments/{visit.pk}/invoice/transactions/', {
        'transaction_type': 'payment', 'amount': '10', 'payment_method': 'cash',
    })
    assert payment.status_code == 201
    assert PaymentTransaction.objects.get(pk=payment.data['id']).clinic_id == clinic.pk


@pytest.mark.parametrize('field', ['patient', 'appointment'])
def test_xray_upload_rejects_foreign_relations_before_storage(world, field, settings):
    settings.XRAY_CLOUD_UPLOAD_ENABLED = True
    data = {'patient': world['patients'][0].pk, 'image_file': png()}
    data[field] = world['patients' if field == 'patient' else 'appointments'][1].pk
    with patch('cloudinary.uploader.upload') as upload:
        response = world['client'].post('/api/xrays/', data, format='multipart')
    assert response.status_code == 400
    upload.assert_not_called()


def test_xray_upload_assigns_clinic(world, settings):
    settings.XRAY_CLOUD_UPLOAD_ENABLED = False
    response = world['client'].post('/api/xrays/', {
        'patient': world['patients'][0].pk, 'image_file': png(),
    }, format='multipart')
    assert response.status_code == 201
    assert XRay.objects.get(pk=response.data['id']).clinic_id == world['clinics'][0].pk


def test_foreign_mutations_are_hidden_and_do_not_touch_storage(world):
    visit, patient = world['appointments'][1], world['patients'][1]
    client = world['client']
    assert client.patch(f'/api/patients/{patient.pk}/', {'full_name': 'Hacked'}).status_code == 404
    assert client.patch(f'/api/appointments/{visit.pk}/', {'notes': 'Hacked'}).status_code == 404
    assert client.patch(f'/api/appointments/{visit.pk}/invoice/', {'notes': 'Hacked'}).status_code == 404
    assert client.post(f'/api/appointments/{visit.pk}/invoice/items/', {
        'description': 'Hacked', 'unit_price': '10',
    }).status_code == 404
    assert client.post(f'/api/appointments/{visit.pk}/invoice/transactions/', {
        'transaction_type': 'refund', 'amount': '10', 'payment_method': 'cash',
    }).status_code == 404
    assert client.delete(
        f'/api/appointments/{visit.pk}/invoice/items/{world["items"][1].pk}/',
    ).status_code == 404
    with patch('cloudinary.uploader.destroy') as destroy:
        assert client.delete(f'/api/xrays/{world["images"][1].pk}/').status_code == 404
    destroy.assert_not_called()
    patient.refresh_from_db()
    assert patient.full_name == 'Shared Name'
    assert PaymentTransaction.objects.count() == 2


def test_foreign_staff_status_is_hidden(world):
    assert world['client'].patch(
        f'/api/accounts/staff/{world["users"][1].pk}/status/', {'is_active': False},
    ).status_code == 404


def test_deactivation_only_affects_selected_membership(world):
    dentist = world['dentists'][0]
    other = ClinicMembership.objects.create(
        user=dentist, clinic=world['clinics'][1], role='dentist',
    )
    response = world['client'].patch(
        f'/api/accounts/staff/{dentist.pk}/status/', {'is_active': False},
    )
    assert response.status_code == 200
    dentist.refresh_from_db()
    other.refresh_from_db()
    assert dentist.is_active and other.is_active
    assert not ClinicMembership.objects.get(user=dentist, clinic=world['clinics'][0]).is_active


def test_superuser_flag_does_not_override_selected_membership_role(world):
    user = world['users'][0]
    user.is_superuser = True
    user.save()
    membership = ClinicMembership.objects.get(user=user, clinic=world['clinics'][0])
    membership.role = 'dentist'
    membership.save()
    response = world['client'].get('/api/accounts/me/')
    assert response.data['role'] == 'dentist'
    assert response.data['is_staff'] is False
    assert world['client'].post('/api/patients/', {'full_name': 'Denied'}).status_code == 403


def test_foreign_clinic_header_is_denied(world):
    world['client'].credentials(HTTP_X_CLINIC_ID=str(world['clinics'][1].pk))
    assert world['client'].get('/api/patients/').status_code == 403


def test_shared_user_switches_clinic_and_role(world):
    ClinicMembership.objects.create(
        user=world['users'][0], clinic=world['clinics'][1], role='receptionist',
    )
    world['client'].credentials()
    assert world['client'].get('/api/patients/').status_code == 403
    world['client'].credentials(HTTP_X_CLINIC_ID=str(world['clinics'][1].pk))
    assert world['client'].get('/api/accounts/me/').data['role'] == 'receptionist'
    assert [p['id'] for p in world['client'].get('/api/patients/').data] == [world['patients'][1].pk]


def test_jwt_cannot_retain_access_after_membership_revoked(world):
    token = AccessToken.for_user(world['users'][0])
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f'Bearer {token}',
        HTTP_X_CLINIC_ID=str(world['clinics'][0].pk),
    )
    assert client.get('/api/patients/').status_code == 200
    ClinicMembership.objects.filter(user=world['users'][0]).update(is_active=False)
    assert client.get('/api/patients/').status_code == 403


def test_new_staff_receives_only_requesting_clinic_membership(world):
    response = world['client'].post('/api/accounts/register/', {
        'username': 'new-clinic-dentist', 'password': 'UniqueStrong!2026', 'role': 'dentist',
    })
    assert response.status_code == 201
    membership = ClinicMembership.objects.get(user_id=response.data['id'])
    assert membership.clinic_id == world['clinics'][0].pk
    assert response.data['role'] == 'dentist'


def test_django_admin_requires_platform_superuser_and_clinical_edits_are_disabled(world):
    request = RequestFactory().get('/admin/')
    request.user = world['users'][0]
    assert admin.site.has_permission(request) is False
    request.user.is_superuser = True
    assert admin.site.has_permission(request) is True
    for model in (PatientProfile, Appointment, InvoiceLineItem, PaymentTransaction, XRay):
        model_admin = admin.site._registry[model]
        assert not model_admin.has_add_permission(request)
        assert not model_admin.has_change_permission(request)
        assert not model_admin.has_delete_permission(request)


def test_import_resolves_names_only_in_selected_clinic(world, tmp_path):
    source = tmp_path / 'xrays.json'
    # json file is created only within pytest's temporary directory.
    source.write_text(json.dumps([{
        'patient_name': 'Shared Name', 'xray_id': 'machine-1',
        'image_url': 'https://example.com/scan.jpg',
    }]))
    call_command('import_xrays', clinic=world['clinics'][0].pk, source=str(source), stdout=StringIO())
    record = XRay.objects.get(external_id='machine-1')
    assert record.clinic_id == world['clinics'][0].pk
    assert record.patient_id == world['patients'][0].pk


def test_import_requires_clinic(world):
    with pytest.raises(CommandError):
        call_command('import_xrays', source='unused.json')


def test_unassigned_patient_is_rejected_before_it_can_be_exposed(world):
    with pytest.raises(IntegrityError), transaction.atomic():
        PatientProfile.objects.create(full_name='Unassigned')
    assert [p['id'] for p in world['client'].get('/api/patients/').data] == [world['patients'][0].pk]


def test_booking_filter_choices_are_clinic_scoped(world):
    from appointments.filters import AppointmentFilter
    from rest_framework.request import Request
    request = Request(RequestFactory().get('/api/appointments/'))
    request.user = world['users'][0]
    filters = AppointmentFilter(request=request, queryset=Appointment.objects.all())
    assert set(filters.form.fields['dentist'].queryset.values_list('pk', flat=True)) == {world['dentists'][0].pk}
    assert set(filters.form.fields['patient'].queryset.values_list('pk', flat=True)) == {world['patients'][0].pk}


def test_import_rejects_ambiguous_names_within_clinic(world, tmp_path):
    PatientProfile.objects.create(clinic=world['clinics'][0], full_name='Shared Name')
    source = tmp_path / 'ambiguous.json'
    source.write_text(json.dumps([{'patient_name': 'Shared Name', 'xray_id': 'ambiguous'}]))
    output = StringIO()
    call_command('import_xrays', clinic=world['clinics'][0].pk, source=str(source), stdout=output)
    assert 'Errors: 1' in output.getvalue()
    assert not XRay.objects.filter(external_id='ambiguous').exists()
