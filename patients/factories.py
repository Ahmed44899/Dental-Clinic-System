import factory
from .models import PatientProfile


class PatientProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PatientProfile

    full_name = factory.Faker('name')
    phone = factory.Faker('phone_number')
    email = factory.Faker('email')
    date_of_birth = factory.Faker('date_of_birth', minimum_age=5, maximum_age=90)
    blood_type = 'O+'