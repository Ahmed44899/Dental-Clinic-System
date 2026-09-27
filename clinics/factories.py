from .models import Clinic


def default_clinic():
    return Clinic.objects.get_or_create(
        slug='test-clinic', defaults={'name': 'Test clinic'},
    )[0]
