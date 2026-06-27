import pytest
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from accounts.factories import CustomUserFactory
from patients.factories import PatientProfileFactory
from .factories import XRayFactory
from .models import XRay


def create_test_image():
    """
    Creates a tiny valid in-memory image file for upload tests.
    We never want real image files sitting in our test suite.
    """
    from PIL import Image
    import io

    image = Image.new('RGB', (10, 10), color='white')
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG')
    buffer.seek(0)
    return SimpleUploadedFile('test_xray.jpg', buffer.read(), content_type='image/jpeg')


@pytest.mark.django_db
class TestXRayAPI:

    def setup_method(self):
        self.client = APIClient()
        self.user = CustomUserFactory()
        self.client.force_authenticate(user=self.user)
        self.patient = PatientProfileFactory()

    def test_upload_xray_with_image(self):
        url = reverse('xray-list-create')
        data = {
            'patient': self.patient.id,
            'image_file': create_test_image(),
            'description': 'Upper molar scan',
        }
        response = self.client.post(url, data, format='multipart')

        assert response.status_code == status.HTTP_201_CREATED
        assert XRay.objects.count() == 1
        xray = XRay.objects.first()
        assert xray.patient == self.patient
        assert xray.image_local  # file was actually saved

    def test_list_xrays_filtered_by_patient(self):
        other_patient = PatientProfileFactory()
        XRayFactory(patient=self.patient)
        XRayFactory(patient=self.patient)
        XRayFactory(patient=other_patient)  # should NOT appear in filtered results

        url = reverse('xray-list-create')
        response = self.client.get(url, {'patient': self.patient.id})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2

    def test_xray_cannot_be_updated(self):
        """We designed XRayDetailView as Retrieve+Destroy only — no update allowed."""
        xray = XRayFactory(patient=self.patient)
        url = reverse('xray-detail', kwargs={'pk': xray.pk})
        response = self.client.patch(url, {'description': 'changed'})

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_delete_xray(self):
        xray = XRayFactory(patient=self.patient)
        url = reverse('xray-detail', kwargs={'pk': xray.pk})
        response = self.client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not XRay.objects.filter(pk=xray.pk).exists() #make sure it is false

    def test_unauthenticated_user_cannot_upload(self):
        client = APIClient()  # no auth
        url = reverse('xray-list-create')
        data = {'patient': self.patient.id, 'image_file': create_test_image()}
        response = client.post(url, data, format='multipart')

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_duplicate_external_id_for_same_patient_rejected(self):
        """Tests the unique_together constraint we set on the model."""
        XRayFactory(patient=self.patient, external_id='DUPLICATE001')

        with pytest.raises(Exception):  # IntegrityError at DB level
            XRayFactory(patient=self.patient, external_id='DUPLICATE001')