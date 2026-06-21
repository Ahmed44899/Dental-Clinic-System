import factory
from django.utils import timezone
from datetime import timedelta
from .models import Appointment
from patients.factories import PatientProfileFactory
from accounts.factories import DentistFactory, CustomUserFactory


class AppointmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Appointment

    patient = factory.SubFactory(PatientProfileFactory) #subfactory for giving a factory to a variable
    dentist = factory.SubFactory(DentistFactory)
    created_by = factory.SubFactory(CustomUserFactory)
    date_time = factory.LazyFunction(lambda: timezone.now() + timedelta(days=1))
    chief_complaint = factory.Faker('sentence')
    status = 'scheduled'