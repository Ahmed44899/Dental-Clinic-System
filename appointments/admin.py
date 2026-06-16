from django.contrib import admin
from .models import Appointment, Invoice


class InvoiceInline(admin.StackedInline):
    """Shows Invoice directly inside the Appointment admin page."""
    model = Invoice
    extra = 0  # don't show empty extra forms


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['patient', 'dentist', 'date_time', 'status', 'created_at']
    list_filter = ['status', 'dentist']
    search_fields = ['patient__full_name', 'dentist__first_name']
    inlines = [InvoiceInline]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['appointment', 'total_fees', 'amount_paid', 'status']
    list_filter = ['status', 'payment_method']