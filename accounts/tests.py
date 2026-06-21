import pytest
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse
from .factories import CustomUserFactory, DentistFactory


@pytest.mark.django_db  # tells pytest this test needs database access
class TestUserRegistration:

    def setup_method(self):
        """Runs before every test method — like a fresh start each time."""
        self.client = APIClient()
        self.admin = CustomUserFactory(role='admin', is_staff=True)

    def test_admin_can_register_new_staff(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse('register')
        data = {
            'username': 'newdentist',
            'email': 'newdentist@clinic.com',
            'password': 'securepass123',
            'role': 'dentist',
            'specialization': 'Orthodontics',
        }
        response = self.client.post(url, data)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['username'] == 'newdentist'
        # password should NEVER appear in the response
        assert 'password' not in response.data

    def test_non_admin_cannot_register_staff(self):
        regular_user = CustomUserFactory(role='receptionist')
        self.client.force_authenticate(user=regular_user)
        url = reverse('register')
        data = {'username': 'hacker', 'password': 'pass12345', 'role': 'dentist'}
        response = self.client.post(url, data)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_user_cannot_register_staff(self):
        url = reverse('register')
        data = {'username': 'hacker', 'password': 'pass12345'}
        response = self.client.post(url, data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestLogin:

    def test_user_can_login_with_correct_credentials(self):
        client = APIClient()
        CustomUserFactory(username='ahmed', password='mypassword123')
        url = reverse('login')
        response = client.post(url, {'username': 'ahmed', 'password': 'mypassword123'})

        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'refresh' in response.data

    def test_login_fails_with_wrong_password(self):
        client = APIClient()
        CustomUserFactory(username='ahmed', password='correctpass')
        url = reverse('login')
        response = client.post(url, {'username': 'ahmed', 'password': 'wrongpass'})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED