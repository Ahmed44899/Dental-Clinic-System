"""Query-growth regressions for clinic-scoped response membership metadata."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory

from accounts.serializers import StaffDirectorySerializer
from appointments.models import Appointment, InvoiceLineItem, PaymentTransaction
from clinics.api import clinic_for
from clinics.models import Clinic, ClinicMembership
from clinics.querysets import membership_prefetch
from patients.models import PatientProfile

pytestmark = pytest.mark.django_db


@pytest.fixture
def clinic_data():
    User = get_user_model()
    clinic = Clinic.objects.create(name='Selected', slug='query-selected')
    other = Clinic.objects.create(name='Other', slug='query-other')
    owner = User.objects.create_user(username='query-owner', role='receptionist')
    ClinicMembership.objects.create(clinic=clinic, user=owner, role='admin')
    ClinicMembership.objects.create(clinic=other, user=owner, role='receptionist')
    patient = PatientProfile.objects.create(clinic=clinic, full_name='Synthetic patient')
    client = APIClient()
    client.force_authenticate(owner)
    client.credentials(HTTP_X_CLINIC_ID=str(clinic.pk))

    def add_actor(index, invoice=None):
        actor = User.objects.create_user(username=f'query-actor-{index}', role='receptionist')
        ClinicMembership.objects.create(clinic=clinic, user=actor, role='dentist')
        ClinicMembership.objects.create(clinic=other, user=actor, role='admin')
        if invoice is None:
            appointment = Appointment.objects.create(
                clinic=clinic, patient=patient, dentist=actor,
                date_time=timezone.now() - timedelta(days=index + 1), status='completed',
            )
            invoice = appointment.invoice
        InvoiceLineItem.objects.create(
            clinic=clinic, invoice=invoice, description='Synthetic charge',
            unit_price=100, created_by=actor,
        )
        PaymentTransaction.objects.create(
            clinic=clinic, invoice=invoice, transaction_type='payment', amount=10,
            payment_method='cash', recorded_by=actor, occurred_at=timezone.now(),
        )
        return actor, invoice

    return SimpleNamespace(clinic=clinic, other=other, owner=owner, client=client, add_actor=add_actor)


def fetch(client, path):
    with CaptureQueriesContext(connection) as queries:
        response = client.get(path)
    assert response.status_code == 200
    return response.data, len(queries)


@pytest.mark.parametrize('endpoint', ['staff', 'dentists', 'appointments', 'invoice', 'items', 'transactions'])
def test_response_query_count_does_not_grow_with_users(clinic_data, endpoint):
    world = clinic_data
    _, invoice = world.add_actor(0)
    root = f'/api/appointments/{invoice.appointment_id}/invoice/'
    path = {
        'staff': '/api/accounts/staff/', 'dentists': '/api/accounts/dentists/',
        'appointments': '/api/appointments/', 'invoice': root,
        'items': root + 'items/', 'transactions': root + 'transactions/',
    }[endpoint]
    _, small_count = fetch(world.client, path)
    for index in range(1, 6):
        world.add_actor(index, invoice if endpoint in {'invoice', 'items', 'transactions'} else None)
    data, large_count = fetch(world.client, path)
    assert large_count == small_count, (endpoint, small_count, large_count)
    print(f'{endpoint}: {small_count} queries for small list; {large_count} for expanded list')

    if endpoint in {'staff', 'dentists'}:
        actors = [row for row in data if row['id'] != world.owner.pk]
        assert len(actors) == 6
        assert all(row['role'] == 'dentist' and row['is_active'] for row in actors)
    elif endpoint == 'appointments':
        assert len(data) == 6
        assert all(row['dentist_detail']['role'] == 'dentist' for row in data)
        assert all(row['invoice']['line_items'][0]['created_by']['role'] == 'dentist' for row in data)
        assert all(row['invoice']['transactions'][0]['recorded_by']['role'] == 'dentist' for row in data)
    elif endpoint == 'invoice':
        assert len(data['line_items']) == len(data['transactions']) == 6
        assert all(row['created_by']['role'] == 'dentist' for row in data['line_items'])
        assert all(row['recorded_by']['role'] == 'dentist' for row in data['transactions'])
    else:
        assert len(data) == 6
        key = 'created_by' if endpoint == 'items' else 'recorded_by'
        assert all(row[key]['role'] == 'dentist' for row in data)


def test_membership_changes_are_visible_on_the_next_request(clinic_data):
    actor, _ = clinic_data.add_actor(0)
    first, _ = fetch(clinic_data.client, '/api/accounts/staff/')
    assert next(row for row in first if row['id'] == actor.pk)['role'] == 'dentist'
    ClinicMembership.objects.filter(clinic=clinic_data.clinic, user=actor).update(
        role='receptionist', is_active=False,
    )
    second, _ = fetch(clinic_data.client, '/api/accounts/staff/')
    row = next(row for row in second if row['id'] == actor.pk)
    assert row['role'] == 'receptionist' and row['is_active'] is False
    assert ClinicMembership.objects.get(clinic=clinic_data.other, user=actor).role == 'admin'


@pytest.mark.parametrize('has_local_membership', [True, False])
def test_prefetched_user_reused_for_other_clinic_gets_correct_role(clinic_data, has_local_membership):
    actor, _ = clinic_data.add_actor(0)
    if not has_local_membership:
        ClinicMembership.objects.filter(user=actor, clinic=clinic_data.clinic).delete()
    actor = get_user_model().objects.prefetch_related(
        membership_prefetch(clinic_data.clinic),
    ).get(pk=actor.pk)
    requests = []
    for clinic in (clinic_data.clinic, clinic_data.other):
        request = APIRequestFactory().get('/', HTTP_X_CLINIC_ID=str(clinic.pk))
        request.user = clinic_data.owner
        clinic_for(request)  # Resolve authorization before measuring serialization.
        requests.append(request)
    with CaptureQueriesContext(connection) as queries:
        local = StaffDirectorySerializer(actor, context={'request': requests[0]}).data
    assert len(queries) == 0
    assert local['role'] == ('dentist' if has_local_membership else None)
    other = StaffDirectorySerializer(actor, context={'request': requests[1]}).data
    assert other['role'] == 'admin' and other['is_active']


def test_missing_ledger_actor_still_serializes_as_null(clinic_data):
    actor, invoice = clinic_data.add_actor(0)
    invoice.line_items.update(created_by=None)
    invoice.transactions.update(recorded_by=None)
    data, _ = fetch(clinic_data.client, f'/api/appointments/{invoice.appointment_id}/invoice/')
    assert data['line_items'][0]['created_by'] is None
    assert data['transactions'][0]['recorded_by'] is None


def test_new_staff_write_response_has_new_membership(clinic_data):
    response = clinic_data.client.post('/api/accounts/register/', {
        'username': 'new-query-dentist', 'password': 'Synthetic-only-frost!9247-lantern',
        'role': 'dentist',
    }, format='json')
    assert response.status_code == 201
    assert response.data['role'] == 'dentist' and response.data['is_staff'] is False
