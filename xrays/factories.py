import factory
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import XRay
from patients.factories import PatientProfileFactory


class XRayFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = XRay

    patient = factory.SubFactory(PatientProfileFactory)
    storage_type = 'local'
    source = 'manual'
    external_id = factory.Sequence(lambda n: f'XR{n:04d}')
    description = factory.Faker('sentence')