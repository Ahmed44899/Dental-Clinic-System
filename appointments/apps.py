from django.apps import AppConfig
from django.db.models.signals import post_save


class AppointmentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'appointments'

    def ready(self):
        from .models import Appointment
        from . import signals
        post_save.connect(signals.create_invoice_on_appointment, sender=Appointment)  # tells Django to load the signals