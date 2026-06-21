import pytest
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse
from accounts.factories import CustomUserFactory
from .factories import PatientProfileFactory
from .models import PatientProfile


@pytest.mark.django_db
class TestPatientAPI:

    def setup_method(self):
        self.client = APIClient()
        self.user = CustomUserFactory()
        self.client.force_authenticate(user=self.user)

    def test_create_patient(self):
        url = reverse('patient-list-create')
        data = {
            'full_name': 'Ahmed Hassan',
            'phone': '01012345678',
            'email': 'ahmed.h@email.com',
            'date_of_birth': '1990-05-15',
            'blood_type': 'A+',
        }
        response = self.client.post(url, data)

        assert response.status_code == status.HTTP_201_CREATED
        assert PatientProfile.objects.count() == 1
        assert response.data['full_name'] == 'Ahmed Hassan'

    def test_age_is_calculated_automatically(self):
        from datetime import date
        patient = PatientProfileFactory(date_of_birth=date(1990, 1, 1))
        url = reverse('patient-detail', kwargs={'pk': patient.pk})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # age should be calculated, not stored
        assert response.data['age'] is not None

    def test_invalid_phone_number_rejected(self):
        url = reverse('patient-list-create')
        data = {'full_name': 'Test Patient', 'phone': 'not-a-phone!!!'}
        response = self.client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'phone' in response.data

    def test_search_finds_patient_by_name(self):
        PatientProfileFactory(full_name='Ahmed Mostafa')
        PatientProfileFactory(full_name='Sara Ali')

        url = reverse('patient-list-create')
        response = self.client.get(url, {'search': 'Ahmed'})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['full_name'] == 'Ahmed Mostafa'

    def test_unauthenticated_request_rejected(self):
        client = APIClient()  # no authentication
        url = reverse('patient-list-create')
        response = client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED