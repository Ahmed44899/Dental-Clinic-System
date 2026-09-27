from clinics.admin_support import ReadOnlyClinicalAdminMixin

from django.contrib import admin
from .models import Appointment, Invoice, InvoiceLineItem, PaymentTransaction


class InvoiceInline(ReadOnlyClinicalAdminMixin, admin.StackedInline):
    """Shows Invoice directly inside the Appointment admin page."""
    model = Invoice
    extra = 0  # don't show empty extra forms
    fields = ['currency', 'notes']


@admin.register(Appointment)
class AppointmentAdmin(ReadOnlyClinicalAdminMixin, admin.ModelAdmin):
    list_display = ['patient', 'dentist', 'date_time', 'status', 'created_at']
    list_filter = ['status', 'dentist']
    search_fields = ['patient__full_name', 'dentist__first_name']
    inlines = [InvoiceInline]


@admin.register(Invoice)
class InvoiceAdmin(ReadOnlyClinicalAdminMixin, admin.ModelAdmin):
    list_display = ['appointment', 'currency', 'total', 'net_paid', 'status']
    list_filter = ['currency']


@admin.register(InvoiceLineItem)
class InvoiceLineItemAdmin(ReadOnlyClinicalAdminMixin, admin.ModelAdmin):
    list_display = ['invoice', 'description', 'quantity', 'unit_price', 'total']
    search_fields = ['description', 'procedure_code', 'invoice__appointment__patient__full_name']


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(ReadOnlyClinicalAdminMixin, admin.ModelAdmin):
    list_display = [
        'invoice', 'transaction_type', 'amount', 'payment_method',
        'occurred_at', 'recorded_by',
    ]
    list_filter = ['transaction_type', 'payment_method', 'invoice__currency']

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
