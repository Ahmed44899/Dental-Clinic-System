import pytest
from django.core.cache import cache
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

    def test_registration_applies_django_password_validators(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(reverse('register'), {
            'username': 'weakpassworduser',
            'password': 'password',
            'role': 'receptionist',
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'password' in response.data


@pytest.mark.django_db
class TestLogin:

    def setup_method(self):
        cache.clear()

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

    def test_admin_role_can_register_staff_without_django_staff_flag(self):
        client = APIClient()
        clinic_admin = CustomUserFactory(role='admin', is_staff=False)
        client.force_authenticate(user=clinic_admin)

        response = client.post(reverse('register'), {
            'username': 'newreception',
            'password': 'securepass123',
            'role': 'receptionist',
        })

        assert response.status_code == status.HTTP_201_CREATED

    def test_authenticated_user_can_get_their_profile(self):
        client = APIClient()
        user = CustomUserFactory(role='dentist', first_name='Mina')
        client.force_authenticate(user=user)

        response = client.get(reverse('current-user'))

        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == user.id
        assert response.data['role'] == 'dentist'
        assert 'password' not in response.data


@pytest.mark.django_db
class TestStaffDirectory:

    def setup_method(self):
        cache.clear()
        self.client = APIClient()
        self.user = CustomUserFactory(role='receptionist')
        self.client.force_authenticate(user=self.user)

    def test_staff_directory_omits_sensitive_account_fields(self):
        DentistFactory(
            email='private@clinic.com',
            phone='01000000000',
            license_number='PRIVATE-LICENSE',
        )

        response = self.client.get(reverse('staff-list'))

        assert response.status_code == status.HTTP_200_OK
        dentist = next(member for member in response.data if member['role'] == 'dentist')
        assert 'email' not in dentist
        assert 'phone' not in dentist
        assert 'license_number' not in dentist
        assert 'is_staff' not in dentist
        assert 'password' not in dentist

    def test_inactive_dentists_are_not_assignable(self):
        active = DentistFactory(is_active=True)
        inactive = DentistFactory(is_active=False)

        response = self.client.get(reverse('dentist-list'))

        returned_ids = {dentist['id'] for dentist in response.data}
        assert active.id in returned_ids
        assert inactive.id not in returned_ids


@pytest.mark.django_db
class TestTokenLifecycle:

    def setup_method(self):
        cache.clear()
        self.client = APIClient()
        self.user = CustomUserFactory(
            username='lifecycle-user',
            password='OriginalSafe!2026',
        )

    def login(self, password='OriginalSafe!2026'):
        return self.client.post(reverse('login'), {
            'username': self.user.username,
            'password': password,
        })

    def test_logout_blacklists_refresh_token(self):
        refresh = self.login().data['refresh']

        logout_response = self.client.post(reverse('logout'), {'refresh': refresh})
        refresh_response = self.client.post(reverse('token-refresh'), {'refresh': refresh})

        assert logout_response.status_code == status.HTTP_205_RESET_CONTENT
        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_refresh_rotation_blacklists_previous_refresh_token(self):
        old_refresh = self.login().data['refresh']

        rotation_response = self.client.post(
            reverse('token-refresh'),
            {'refresh': old_refresh},
        )
        reused_response = self.client.post(
            reverse('token-refresh'),
            {'refresh': old_refresh},
        )

        assert rotation_response.status_code == status.HTTP_200_OK
        assert 'refresh' in rotation_response.data
        assert rotation_response.data['refresh'] != old_refresh
        assert reused_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_password_change_revokes_existing_access_and_refresh_tokens(self):
        login_response = self.login()
        access = login_response.data['access']
        refresh = login_response.data['refresh']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

        change_response = self.client.post(reverse('password-change'), {
            'old_password': 'OriginalSafe!2026',
            'new_password': 'ReplacementSafe!2026',
        })
        old_access_response = self.client.get(reverse('current-user'))
        self.client.credentials()
        old_refresh_response = self.client.post(
            reverse('token-refresh'),
            {'refresh': refresh},
        )
        new_login_response = self.login('ReplacementSafe!2026')

        assert change_response.status_code == status.HTTP_200_OK
        assert old_access_response.status_code == status.HTTP_401_UNAUTHORIZED
        assert old_refresh_response.status_code == status.HTTP_401_UNAUTHORIZED
        assert new_login_response.status_code == status.HTTP_200_OK

    def test_password_change_requires_current_password(self):
        access = self.login().data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

        response = self.client.post(reverse('password-change'), {
            'old_password': 'WrongCurrentPassword!2026',
            'new_password': 'ReplacementSafe!2026',
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'old_password' in response.data

    def test_login_is_throttled_after_repeated_failures(self):
        responses = [
            self.client.post(reverse('login'), {
                'username': self.user.username,
                'password': 'wrong-password',
            })
            for _ in range(6)
        ]

        assert all(response.status_code == status.HTTP_401_UNAUTHORIZED for response in responses[:5])
        assert responses[5].status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
class TestStaffAccountLifecycle:

    def setup_method(self):
        self.client = APIClient()
        self.admin = CustomUserFactory(role='admin', is_staff=True)
        self.target = CustomUserFactory(role='receptionist', is_active=True)
        self.client.force_authenticate(user=self.admin)

    def test_admin_can_deactivate_staff_account(self):
        response = self.client.patch(
            reverse('staff-status', kwargs={'pk': self.target.pk}),
            {'is_active': False},
        )

        assert response.status_code == status.HTTP_200_OK
        self.target.refresh_from_db()
        assert self.target.is_active is True
        assert self.target.clinic_memberships.get().is_active is False

    def test_admin_cannot_deactivate_own_account(self):
        response = self.client.patch(
            reverse('staff-status', kwargs={'pk': self.admin.pk}),
            {'is_active': False},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        self.admin.refresh_from_db()
        assert self.admin.is_active is True

    def test_non_admin_cannot_change_staff_status(self):
        receptionist = CustomUserFactory(role='receptionist')
        self.client.force_authenticate(user=receptionist)

        response = self.client.patch(
            reverse('staff-status', kwargs={'pk': self.target.pk}),
            {'is_active': False},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_directory_includes_inactive_staff(self):
        self.target.is_active = False
        self.target.save(update_fields=['is_active'])

        response = self.client.get(reverse('staff-list'))

        returned = {member['id']: member for member in response.data}
        assert returned[self.target.id]['is_active'] is False
