import pytest
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from django.db import IntegrityError, transaction
from accounts.factories import CustomUserFactory, DentistFactory
from patients.factories import PatientProfileFactory
from .factories import AppointmentFactory
from .models import Appointment, Invoice, InvoiceLineItem, PaymentTransaction


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

    def test_dentist_cannot_be_double_booked_at_the_same_time(self):
        date_time = timezone.now() + timedelta(days=2)
        AppointmentFactory(dentist=self.dentist, date_time=date_time, status='scheduled')
        response = self.client.post(reverse('appointment-list-create'), {
            'patient': self.patient.id,
            'dentist': self.dentist.id,
            'date_time': date_time.isoformat(),
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'date_time' in response.data

    def test_dentist_cannot_be_booked_for_overlapping_time_ranges(self):
        date_time = timezone.now() + timedelta(days=2)
        AppointmentFactory(
            dentist=self.dentist,
            date_time=date_time,
            duration_minutes=60,
        )

        response = self.client.post(reverse('appointment-list-create'), {
            'patient': self.patient.id,
            'dentist': self.dentist.id,
            'date_time': (date_time + timedelta(minutes=30)).isoformat(),
            'duration_minutes': 30,
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'overlaps' in str(response.data['date_time'][0])

    def test_appointment_may_start_when_previous_visit_ends(self):
        date_time = timezone.now() + timedelta(days=2)
        AppointmentFactory(
            dentist=self.dentist,
            date_time=date_time,
            duration_minutes=30,
        )

        response = self.client.post(reverse('appointment-list-create'), {
            'patient': self.patient.id,
            'dentist': self.dentist.id,
            'date_time': (date_time + timedelta(minutes=30)).isoformat(),
            'duration_minutes': 30,
        })

        assert response.status_code == status.HTTP_201_CREATED

    def test_two_dentists_may_be_booked_at_the_same_time(self):
        date_time = timezone.now() + timedelta(days=2)
        other_dentist = DentistFactory()
        AppointmentFactory(
            dentist=self.dentist,
            date_time=date_time,
            duration_minutes=60,
        )

        response = self.client.post(reverse('appointment-list-create'), {
            'patient': self.patient.id,
            'dentist': other_dentist.id,
            'date_time': date_time.isoformat(),
            'duration_minutes': 60,
        })

        assert response.status_code == status.HTTP_201_CREATED

    def test_emergency_overbook_may_overlap_same_dentist(self):
        date_time = timezone.now() + timedelta(days=2)
        AppointmentFactory(
            dentist=self.dentist,
            date_time=date_time,
            duration_minutes=60,
        )

        response = self.client.post(reverse('appointment-list-create'), {
            'patient': self.patient.id,
            'dentist': self.dentist.id,
            'date_time': (date_time + timedelta(minutes=15)).isoformat(),
            'duration_minutes': 30,
            'is_emergency_overbook': True,
            'emergency_reason': 'Acute facial swelling and severe pain',
        })

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['is_emergency_overbook'] is True

    def test_emergency_overbook_requires_reason(self):
        response = self.client.post(reverse('appointment-list-create'), {
            'patient': self.patient.id,
            'dentist': self.dentist.id,
            'date_time': (timezone.now() + timedelta(days=2)).isoformat(),
            'is_emergency_overbook': True,
            'emergency_reason': '   ',
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'emergency_reason' in response.data

    def test_emergency_overbooking_list_filter(self):
        emergency = AppointmentFactory(
            is_emergency_overbook=True,
            emergency_reason='Trauma',
        )
        AppointmentFactory(is_emergency_overbook=False)

        response = self.client.get(
            reverse('appointment-list-create'),
            {'is_emergency_overbook': 'true'},
        )

        assert response.status_code == status.HTTP_200_OK
        assert [record['id'] for record in response.data] == [emergency.id]

    def test_cancelled_appointment_releases_its_time(self):
        date_time = timezone.now() + timedelta(days=2)
        AppointmentFactory(
            dentist=self.dentist,
            date_time=date_time,
            duration_minutes=60,
            status='cancelled',
        )

        response = self.client.post(reverse('appointment-list-create'), {
            'patient': self.patient.id,
            'dentist': self.dentist.id,
            'date_time': (date_time + timedelta(minutes=15)).isoformat(),
            'duration_minutes': 30,
        })

        assert response.status_code == status.HTTP_201_CREATED

    @pytest.mark.parametrize('duration', [0, 4, 481])
    def test_invalid_duration_is_rejected(self, duration):
        response = self.client.post(reverse('appointment-list-create'), {
            'patient': self.patient.id,
            'dentist': self.dentist.id,
            'date_time': (timezone.now() + timedelta(days=2)).isoformat(),
            'duration_minutes': duration,
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'duration_minutes' in response.data

    def test_new_appointment_cannot_start_closed(self):
        response = self.client.post(reverse('appointment-list-create'), {
            'patient': self.patient.id,
            'dentist': self.dentist.id,
            'date_time': (timezone.now() + timedelta(days=2)).isoformat(),
            'status': 'cancelled',
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'status' in response.data

    def test_database_rejects_identical_scheduled_start_for_dentist(self):
        date_time = timezone.now() + timedelta(days=2)
        AppointmentFactory(dentist=self.dentist, date_time=date_time)

        with pytest.raises(IntegrityError), transaction.atomic():
            AppointmentFactory(dentist=self.dentist, date_time=date_time)


@pytest.mark.django_db
class TestInvoicePayment:

    def setup_method(self):
        self.client = APIClient()
        self.staff = CustomUserFactory()
        self.client.force_authenticate(user=self.staff)
        self.appointment = AppointmentFactory()
        self.invoice_url = reverse('invoice-detail', kwargs={'pk': self.appointment.pk})
        self.item_url = reverse(
            'invoice-item-list-create', kwargs={'pk': self.appointment.pk}
        )
        self.transaction_url = reverse(
            'payment-transaction-list-create', kwargs={'pk': self.appointment.pk}
        )

    def add_item(self, price='500.00', description='Dental treatment'):
        return self.client.post(self.item_url, {
            'description': description,
            'quantity': '1.00',
            'unit_price': price,
        })

    def add_transaction(self, amount, transaction_type='payment'):
        return self.client.post(self.transaction_url, {
            'transaction_type': transaction_type,
            'amount': amount,
            'payment_method': 'cash',
            'occurred_at': timezone.now().isoformat(),
        })

    def test_paying_full_amount_marks_invoice_as_paid(self):
        assert self.add_item().status_code == status.HTTP_201_CREATED
        assert self.add_transaction('500.00').status_code == status.HTTP_201_CREATED
        response = self.client.get(self.invoice_url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'paid'
        assert response.data['balance'] == '0.00'
        assert response.data['net_paid'] == '500.00'
        assert len(response.data['transactions']) == 1

    def test_paying_partial_amount_marks_invoice_as_partial(self):
        self.add_item()
        self.add_transaction('200.00')
        response = self.client.get(self.invoice_url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'partial'
        assert response.data['balance'] == '300.00'

    def test_overpayment_is_rejected(self):
        self.add_item()
        response = self.add_transaction('600.00')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert PaymentTransaction.objects.count() == 0

    def test_refund_reopens_balance_without_rewriting_payment(self):
        self.add_item()
        self.add_transaction('500.00')
        refund = self.add_transaction('125.00', transaction_type='refund')
        invoice = self.client.get(self.invoice_url)

        assert refund.status_code == status.HTTP_201_CREATED
        assert invoice.data['payments_total'] == '500.00'
        assert invoice.data['refunds_total'] == '125.00'
        assert invoice.data['net_paid'] == '375.00'
        assert invoice.data['balance'] == '125.00'
        assert invoice.data['status'] == 'partial'

    def test_refund_cannot_exceed_net_collections(self):
        self.add_item()
        self.add_transaction('100.00')

        response = self.add_transaction('101.00', transaction_type='refund')

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_negative_line_price_and_zero_payment_are_rejected(self):
        invalid_item = self.add_item(price='-1.00')
        invalid_payment = self.add_transaction('0.00')

        assert invalid_item.status_code == status.HTTP_400_BAD_REQUEST
        assert invalid_payment.status_code == status.HTTP_400_BAD_REQUEST

    def test_currency_can_be_selected_before_financial_activity(self):
        response = self.client.patch(self.invoice_url, {'currency': 'EGP'})

        assert response.status_code == status.HTTP_200_OK
        assert response.data['currency'] == 'EGP'

    def test_currency_cannot_change_after_line_item_is_added(self):
        self.add_item()

        response = self.client.patch(self.invoice_url, {'currency': 'EGP'})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'currency' in response.data

    def test_line_items_lock_after_first_transaction(self):
        item_response = self.add_item()
        self.add_transaction('100.00')
        detail_url = reverse('invoice-item-detail', kwargs={
            'pk': self.appointment.pk,
            'item_pk': item_response.data['id'],
        })

        update = self.client.patch(detail_url, {'unit_price': '600.00'})
        delete = self.client.delete(detail_url)

        assert update.status_code == status.HTTP_400_BAD_REQUEST
        assert delete.status_code == status.HTTP_400_BAD_REQUEST

    def test_payment_transaction_records_staff_and_is_append_only(self):
        self.add_item()
        response = self.add_transaction('100.00')

        assert response.status_code == status.HTTP_201_CREATED
        transaction_record = PaymentTransaction.objects.get(pk=response.data['id'])
        assert transaction_record.recorded_by == self.staff
        assert self.client.patch(
            self.transaction_url, {'amount': '50.00'}
        ).status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_cancelled_appointment_rejects_new_payment_but_allows_refund(self):
        self.add_item()
        self.add_transaction('100.00')
        self.appointment.status = 'cancelled'
        self.appointment.save(update_fields=['status'])

        payment = self.add_transaction('50.00')
        refund = self.add_transaction('50.00', transaction_type='refund')

        assert payment.status_code == status.HTTP_400_BAD_REQUEST
        assert refund.status_code == status.HTTP_201_CREATED

    def test_invoice_line_total_is_calculated_server_side(self):
        response = self.client.post(self.item_url, {
            'description': 'Two restorations',
            'quantity': '2.00',
            'unit_price': '175.50',
        })

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['total'] == '351.00'
        assert InvoiceLineItem.objects.get(pk=response.data['id']).created_by == self.staff

    def test_appointment_and_invoice_cannot_be_cascade_deleted(self):
        response = self.client.delete(
            reverse('appointment-detail', kwargs={'pk': self.appointment.pk})
        )

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert Appointment.objects.filter(pk=self.appointment.pk).exists()
        assert Invoice.objects.filter(appointment=self.appointment).exists()


@pytest.mark.django_db
class TestFinancialReports:

    def setup_method(self):
        self.client = APIClient()
        self.staff = CustomUserFactory()
        self.client.force_authenticate(user=self.staff)
        self.dentist = DentistFactory()
        self.other_dentist = DentistFactory()
        self.today = timezone.now()

    def make_financial_activity(
        self, dentist, currency='USD', status_value='completed',
        revenue='500.00', payment='300.00', refund='0.00', days_ago=0,
    ):
        appointment = AppointmentFactory(
            dentist=dentist,
            status=status_value,
            date_time=self.today - timedelta(days=days_ago, hours=1),
        )
        invoice = appointment.invoice
        invoice.currency = currency
        invoice.save(update_fields=['currency'])
        InvoiceLineItem.objects.create(
            invoice=invoice, clinic=invoice.clinic,
            description='Treatment',
            quantity=Decimal('1.00'),
            unit_price=Decimal(revenue),
            created_by=self.staff,
        )
        if Decimal(payment) > 0:
            PaymentTransaction.objects.create(
                invoice=invoice, clinic=invoice.clinic,
                transaction_type='payment',
                amount=Decimal(payment),
                payment_method='cash',
                occurred_at=self.today - timedelta(days=days_ago),
                recorded_by=self.staff,
            )
        if Decimal(refund) > 0:
            PaymentTransaction.objects.create(
                invoice=invoice, clinic=invoice.clinic,
                transaction_type='refund',
                amount=Decimal(refund),
                payment_method='cash',
                occurred_at=self.today - timedelta(days=days_ago),
                recorded_by=self.staff,
            )
        return appointment

    def report(self, **params):
        defaults = {
            'date_from': (self.today - timedelta(days=30)).date().isoformat(),
            'date_to': self.today.date().isoformat(),
            'currency': 'USD',
        }
        defaults.update(params)
        return self.client.get(reverse('financial-report'), defaults)

    def test_report_separates_revenue_collections_refunds_and_receivables(self):
        self.make_financial_activity(
            self.dentist, revenue='500.00', payment='300.00', refund='50.00'
        )

        response = self.report()

        assert response.status_code == status.HTTP_200_OK
        assert response.data['summary'] == {
            'revenue': '500.00',
            'collections': '300.00',
            'refunds': '50.00',
            'net_collections': '250.00',
            'outstanding': '250.00',
        }

    def test_currency_filter_never_combines_usd_and_egp(self):
        self.make_financial_activity(self.dentist, currency='USD', revenue='100.00')
        self.make_financial_activity(self.dentist, currency='EGP', revenue='900.00')

        usd = self.report(currency='USD')
        egp = self.report(currency='EGP')

        assert usd.data['summary']['revenue'] == '100.00'
        assert egp.data['summary']['revenue'] == '900.00'

    def test_report_can_filter_and_group_by_dentist(self):
        self.make_financial_activity(self.dentist, revenue='100.00')
        self.make_financial_activity(self.other_dentist, revenue='250.00')

        response = self.report(dentist=self.dentist.pk)

        assert response.data['summary']['revenue'] == '100.00'
        assert len(response.data['by_dentist']) == 1
        assert response.data['by_dentist'][0]['dentist_id'] == self.dentist.pk

    def test_scheduled_treatment_is_not_recognized_as_revenue(self):
        self.make_financial_activity(
            self.dentist, status_value='scheduled', revenue='500.00'
        )

        response = self.report()

        assert response.data['summary']['revenue'] == '0.00'
        assert response.data['summary']['collections'] == '300.00'

    def test_dentist_report_is_forced_to_own_activity(self):
        self.make_financial_activity(self.dentist, revenue='100.00')
        self.make_financial_activity(self.other_dentist, revenue='250.00')
        self.client.force_authenticate(user=self.dentist)

        response = self.report(dentist=self.other_dentist.pk)

        assert response.data['summary']['revenue'] == '100.00'
        assert response.data['filters']['dentist'] == self.dentist.pk

    def test_invalid_report_date_range_is_rejected(self):
        response = self.report(
            date_from=self.today.date().isoformat(),
            date_to=(self.today - timedelta(days=1)).date().isoformat(),
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.django_db
class TestAppointmentRolePermissions:

    def setup_method(self):
        self.client = APIClient()
        self.dentist = DentistFactory()
        self.own_appointment = AppointmentFactory(dentist=self.dentist)
        self.other_appointment = AppointmentFactory()
        self.client.force_authenticate(user=self.dentist)

    def test_dentist_lists_only_assigned_appointments(self):
        response = self.client.get(reverse('appointment-list-create'))

        assert response.status_code == status.HTTP_200_OK
        returned_ids = {appointment['id'] for appointment in response.data}
        assert returned_ids == {self.own_appointment.id}

    def test_dentist_cannot_create_appointment(self):
        response = self.client.post(reverse('appointment-list-create'), {
            'patient': PatientProfileFactory().id,
            'dentist': self.dentist.id,
            'date_time': (timezone.now() + timedelta(days=3)).isoformat(),
        })

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_dentist_can_update_own_clinical_outcome(self):
        self.own_appointment.date_time = timezone.now() - timedelta(hours=1)
        self.own_appointment.save(update_fields=['date_time'])
        response = self.client.patch(
            reverse('appointment-detail', kwargs={'pk': self.own_appointment.pk}),
            {
                'status': 'completed',
                'diagnosis': 'Reversible pulpitis',
                'procedures_done': 'Composite restoration',
            },
        )

        assert response.status_code == status.HTTP_200_OK
        self.own_appointment.refresh_from_db()
        assert self.own_appointment.status == 'completed'
        assert self.own_appointment.diagnosis == 'Reversible pulpitis'

    @pytest.mark.parametrize('new_status', ['completed', 'no_show'])
    def test_future_appointment_cannot_be_closed_as_attended(self, new_status):
        response = self.client.patch(
            reverse('appointment-detail', kwargs={'pk': self.own_appointment.pk}),
            {'status': new_status},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'status' in response.data

    @pytest.mark.parametrize('closed_status', ['completed', 'cancelled', 'no_show'])
    def test_closed_appointment_cannot_be_reopened(self, closed_status):
        self.own_appointment.status = closed_status
        self.own_appointment.date_time = timezone.now() - timedelta(days=1)
        self.own_appointment.save(update_fields=['status', 'date_time'])

        response = self.client.patch(
            reverse('appointment-detail', kwargs={'pk': self.own_appointment.pk}),
            {'status': 'scheduled'},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'status' in response.data

    def test_dentist_cannot_reschedule_own_appointment(self):
        response = self.client.patch(
            reverse('appointment-detail', kwargs={'pk': self.own_appointment.pk}),
            {'date_time': (timezone.now() + timedelta(days=5)).isoformat()},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'date_time' in response.data

    def test_dentist_cannot_access_another_dentists_appointment(self):
        response = self.client.get(
            reverse('appointment-detail', kwargs={'pk': self.other_appointment.pk})
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_dentist_can_view_but_not_edit_own_invoice(self):
        url = reverse('invoice-detail', kwargs={'pk': self.own_appointment.pk})

        get_response = self.client.get(url)
        patch_response = self.client.patch(url, {'total_fees': '900.00'})

        assert get_response.status_code == status.HTTP_200_OK
        assert patch_response.status_code == status.HTTP_403_FORBIDDEN

    def test_dentist_cannot_view_another_dentists_invoice(self):
        response = self.client.get(
            reverse('invoice-detail', kwargs={'pk': self.other_appointment.pk})
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_receptionist_cannot_modify_clinical_outcome(self):
        receptionist = CustomUserFactory(role='receptionist')
        self.client.force_authenticate(user=receptionist)

        response = self.client.patch(
            reverse('appointment-detail', kwargs={'pk': self.own_appointment.pk}),
            {'diagnosis': 'Attempted change'},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'diagnosis' in response.data
