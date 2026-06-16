from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Appointment, Invoice


@receiver(post_save, sender=Appointment)
def create_invoice_on_appointment(sender, instance, created, **kwargs):
    """
    Automatically creates an Invoice when a new Appointment is saved.
    `created` is True only on first save, not on updates — so we don't
    create duplicate invoices when the appointment is edited later.
    """
    if created:
        Invoice.objects.create(appointment=instance)