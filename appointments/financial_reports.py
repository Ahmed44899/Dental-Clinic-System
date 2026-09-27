from clinics.api import clinic_for

from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import InvoiceAccessPermission, is_clinic_admin, is_dentist
from .models import Invoice, InvoiceLineItem, PaymentTransaction


ZERO = Decimal('0.00')


def money(value):
    return format(value.quantize(Decimal('0.01')), 'f')


def month_key(value):
    return value.strftime('%Y-%m')


class FinancialReportView(APIView):
    """Revenue and cash collections, always reported in one currency."""

    permission_classes = [InvoiceAccessPermission]

    def get(self, request):
        today = date.today()
        try:
            date_from = date.fromisoformat(
                request.query_params.get('date_from', today.replace(day=1).isoformat())
            )
            date_to = date.fromisoformat(
                request.query_params.get('date_to', today.isoformat())
            )
        except ValueError as exc:
            raise ValidationError({'date': 'Use dates in YYYY-MM-DD format.'}) from exc
        if date_from > date_to:
            raise ValidationError({'date': 'Start date cannot be after end date.'})

        currency = request.query_params.get('currency', 'USD').upper()
        if currency not in dict(Invoice.CURRENCY_CHOICES):
            raise ValidationError({'currency': 'Currency must be USD or EGP.'})

        dentist_id = request.query_params.get('dentist') or None
        if is_dentist(request) and not is_clinic_admin(request):
            dentist_id = request.user.pk
        elif dentist_id:
            try:
                dentist_id = int(dentist_id)
            except ValueError as exc:
                raise ValidationError({'dentist': 'Dentist must be a numeric ID.'}) from exc

        clinic = clinic_for(request)
        invoice_filter = {'invoice__currency': currency, 'clinic': clinic, 'invoice__clinic': clinic, 'invoice__appointment__clinic': clinic}
        direct_invoice_filter = {'currency': currency, 'clinic': clinic, 'appointment__clinic': clinic}
        if dentist_id:
            invoice_filter['invoice__appointment__dentist_id'] = dentist_id
            direct_invoice_filter['appointment__dentist_id'] = dentist_id

        revenue_items = InvoiceLineItem.objects.filter(
            **invoice_filter,
            invoice__appointment__status='completed',
            invoice__appointment__date_time__date__gte=date_from,
            invoice__appointment__date_time__date__lte=date_to,
        ).select_related('invoice__appointment__dentist')
        transactions = PaymentTransaction.objects.filter(
            **invoice_filter,
            occurred_at__date__gte=date_from,
            occurred_at__date__lte=date_to,
        ).select_related('invoice__appointment__dentist')
        invoices = Invoice.objects.filter(
            **direct_invoice_filter,
            appointment__date_time__date__gte=date_from,
            appointment__date_time__date__lte=date_to,
        ).select_related('appointment__dentist').prefetch_related(
            'line_items', 'transactions'
        )

        summary = defaultdict(lambda: ZERO)
        dentist_totals = defaultdict(lambda: defaultdict(lambda: ZERO))
        monthly_totals = defaultdict(lambda: defaultdict(lambda: ZERO))

        for item in revenue_items:
            amount = item.total
            dentist = item.invoice.appointment.dentist
            summary['revenue'] += amount
            dentist_totals[dentist.pk]['revenue'] += amount
            monthly_totals[month_key(item.invoice.appointment.date_time)]['revenue'] += amount

        for entry in transactions:
            amount = entry.amount
            dentist = entry.invoice.appointment.dentist
            key = 'collections' if entry.transaction_type == 'payment' else 'refunds'
            summary[key] += amount
            dentist_totals[dentist.pk][key] += amount
            monthly_totals[month_key(entry.occurred_at)][key] += amount

        for invoice in invoices:
            outstanding = max(invoice.balance, ZERO)
            summary['outstanding'] += outstanding
            dentist_totals[invoice.appointment.dentist_id]['outstanding'] += outstanding

        dentist_ids = set(dentist_totals)
        dentists = {
            dentist.pk: dentist
            for dentist in get_user_model().objects.filter(pk__in=dentist_ids)
        }
        available_dentists = get_user_model().objects.filter(clinic_memberships__clinic=clinic, clinic_memberships__role='dentist').order_by(
            'first_name', 'last_name', 'username'
        )
        if dentist_id:
            available_dentists = available_dentists.filter(pk=dentist_id)

        def net(values):
            return values['collections'] - values['refunds']

        return Response({
            'filters': {
                'date_from': date_from.isoformat(),
                'date_to': date_to.isoformat(),
                'currency': currency,
                'dentist': dentist_id,
            },
            'summary': {
                'revenue': money(summary['revenue']),
                'collections': money(summary['collections']),
                'refunds': money(summary['refunds']),
                'net_collections': money(net(summary)),
                'outstanding': money(summary['outstanding']),
            },
            'by_dentist': [
                {
                    'dentist_id': pk,
                    'dentist_name': dentists[pk].get_full_name() or dentists[pk].username,
                    'revenue': money(values['revenue']),
                    'collections': money(values['collections']),
                    'refunds': money(values['refunds']),
                    'net_collections': money(net(values)),
                    'outstanding': money(values['outstanding']),
                }
                for pk, values in sorted(
                    dentist_totals.items(),
                    key=lambda pair: (dentists[pair[0]].get_full_name() or dentists[pair[0]].username),
                )
            ],
            'by_month': [
                {
                    'month': month,
                    'revenue': money(values['revenue']),
                    'collections': money(values['collections']),
                    'refunds': money(values['refunds']),
                    'net_collections': money(net(values)),
                }
                for month, values in sorted(monthly_totals.items())
            ],
            'dentists': [
                {
                    'id': dentist.pk,
                    'name': dentist.get_full_name() or dentist.username,
                    'is_active': dentist.is_active and dentist.clinic_memberships.get(clinic=clinic).is_active,
                }
                for dentist in available_dentists
            ],
        })
