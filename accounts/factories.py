import factory
from .models import CustomUser

#factory to give ready data to tests.py

class CustomUserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CustomUser
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f'user{n}')
    email = factory.LazyAttribute(lambda obj: f'{obj.username}@clinic.com')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    role = 'receptionist'

    @factory.post_generation
    def clinic(self, create, extracted, **kwargs):
        if create:
            from clinics.factories import default_clinic
            from clinics.models import ClinicMembership
            ClinicMembership.objects.create(
                user=self, clinic=extracted or default_clinic(),
                role=self.role, is_active=self.is_active,
            )

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        """Always hash the password properly, even in test data."""
        password = extracted or 'testpass123'
        self.set_password(password)
        if create:
            self.save()


class DentistFactory(CustomUserFactory):
    """A specialized factory — inherits everything from CustomUserFactory."""
    role = 'dentist'
    specialization = factory.Faker('job')
    license_number = factory.Sequence(lambda n: f'LIC{n:05d}')
