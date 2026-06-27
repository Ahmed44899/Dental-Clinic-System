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


import json
import tempfile
from django.core.management import call_command
from io import StringIO


@pytest.mark.django_db
class TestImportXraysCommand:

    def setup_method(self):
        self.patient = PatientProfileFactory(full_name='Ahmed Ali')

    def _write_temp_json(self, data):
        """Helper — creates a temporary JSON file for the command to read."""
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(data, tmp)
        tmp.close()
        return tmp.name

    def test_import_creates_xray_for_matching_patient(self):
        data = [{
            "xray_id": "XR100",
            "patient_name": "Ahmed Ali",
            "image_url": "https://example.com/test.jpg",
            "taken_at": "2024-01-15T10:30:00Z",
            "description": "Test scan"
        }]
        file_path = self._write_temp_json(data)

        out = StringIO()
        call_command('import_xrays', f'--source={file_path}', stdout=out)

        assert XRay.objects.filter(patient=self.patient, external_id='XR100').exists()
        assert 'Imported: 1' in out.getvalue()

    def test_import_skips_already_imported_xray(self):
        XRayFactory(patient=self.patient, external_id='XR100')

        data = [{
            "xray_id": "XR100",
            "patient_name": "Ahmed Ali",
            "image_url": "https://example.com/test.jpg",
        }]
        file_path = self._write_temp_json(data)

        out = StringIO()
        call_command('import_xrays', f'--source={file_path}', stdout=out)

        # Should still only be 1 record — not duplicated
        assert XRay.objects.filter(patient=self.patient, external_id='XR100').count() == 1
        assert 'Skipped: 1' in out.getvalue()

    def test_import_reports_error_for_unknown_patient(self):
        data = [{
            "xray_id": "XR999",
            "patient_name": "Nobody Real",
            "image_url": "https://example.com/test.jpg",
        }]
        file_path = self._write_temp_json(data)

        out = StringIO()
        call_command('import_xrays', f'--source={file_path}', stdout=out)

        assert not XRay.objects.filter(external_id='XR999').exists()
        assert 'Errors: 1' in out.getvalue()

    def test_dry_run_does_not_save_anything(self):
        data = [{
            "xray_id": "XR200",
            "patient_name": "Ahmed Ali",
            "image_url": "https://example.com/test.jpg",
        }]
        file_path = self._write_temp_json(data)

        out = StringIO()
        call_command('import_xrays', f'--source={file_path}', '--dry-run', stdout=out)

        assert not XRay.objects.filter(external_id='XR200').exists()
        assert 'DRY RUN' in out.getvalue()

    def test_missing_file_reports_error(self):
        out = StringIO()
        call_command('import_xrays', '--source=does_not_exist.json', stdout=out)

        assert 'not found' in out.getvalue().lower()