import pytest
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from accounts.factories import CustomUserFactory, DentistFactory
from patients.factories import PatientProfileFactory
from .factories import AppointmentFactory
from .models import Appointment, Invoice


@pytest.mark.django_db
class TestAppointmentCreation:

    def setup_method(self):
        self.client = APIClient()
        self.staff = CustomUserFactory()
        self.dentist = DentistFactory()
        self.patient = PatientProfileFactory()
        self.client.force_authenticate(user=self.staff)

    def test_creating_appointment_auto_creates_invoice(self):
        """This tests the SIGNAL we wrote — critical to verify it actually fires."""
        url = reverse('appointment-list-create')
        data = {
            'patient': self.patient.id,
            'dentist': self.dentist.id,
            'date_time': (timezone.now() + timedelta(days=1)).isoformat(),
            'chief_complaint': 'Toothache',
        }
        response = self.client.post(url, data)

        assert response.status_code == status.HTTP_201_CREATED
        appointment = Appointment.objects.get(id=response.data['id'])

        # The signal should have created this automatically — we never called Invoice.objects.create()
        assert Invoice.objects.filter(appointment=appointment).exists()
        assert appointment.invoice.status == 'unpaid'

    def test_cannot_book_appointment_in_the_past(self):
        url = reverse('appointment-list-create')
        data = {
            'patient': self.patient.id,
            'dentist': self.dentist.id,
            'date_time': (timezone.now() - timedelta(days=1)).isoformat(),  # yesterday
        }
        response = self.client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'date_time' in response.data

    def test_receptionist_cannot_be_assigned_as_dentist(self):
        receptionist = CustomUserFactory(role='receptionist')
        url = reverse('appointment-list-create')
        data = {
            'patient': self.patient.id,
            'dentist': receptionist.id,  # WRONG — not a dentist
            'date_time': (timezone.now() + timedelta(days=1)).isoformat(),
        }
        response = self.client.post(url, data)

        # Our custom DentistField should reject this
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_created_by_is_set_automatically(self):
        url = reverse('appointment-list-create')
        data = {
            'patient': self.patient.id,
            'dentist': self.dentist.id,
            'date_time': (timezone.now() + timedelta(days=1)).isoformat(),
        }
        response = self.client.post(url, data)
        appointment = Appointment.objects.get(id=response.data['id'])

        assert appointment.created_by == self.staff


@pytest.mark.django_db
class TestInvoicePayment:

    def setup_method(self):
        self.client = APIClient()
        self.staff = CustomUserFactory()
        self.client.force_authenticate(user=self.staff)
        self.appointment = AppointmentFactory()

    def test_paying_full_amount_marks_invoice_as_paid(self):
        url = reverse('invoice-detail', kwargs={'pk': self.appointment.pk})
        data = {'total_fees': '500.00', 'amount_paid': '500.00'}
        response = self.client.patch(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'paid'
        assert response.data['balance'] == '0.00'

    def test_paying_partial_amount_marks_invoice_as_partial(self):
        url = reverse('invoice-detail', kwargs={'pk': self.appointment.pk})
        data = {'total_fees': '500.00', 'amount_paid': '200.00'}
        response = self.client.patch(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'partial'
        assert response.data['balance'] == '300.00'

    def test_overpayment_is_rejected(self):
        url = reverse('invoice-detail', kwargs={'pk': self.appointment.pk})
        data = {'total_fees': '500.00', 'amount_paid': '600.00'}
        response = self.client.patch(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST