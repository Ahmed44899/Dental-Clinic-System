from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('dentist', 'Dentist'),
        ('receptionist', 'Receptionist'),
        ('admin', 'Admin'),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='receptionist')
    phone = models.CharField(max_length=30, blank=True)
    specialization = models.CharField(max_length=120, blank=True)  # for dentists only
    license_number = models.CharField(max_length=50, blank=True, null=True, unique=True)

    def __str__(self):
        return f'{self.get_full_name()} ({self.role})'

    # Convenience properties — very useful in views and serializers
    @property
    def is_dentist(self):
        return self.role == 'dentist'

    @property
    def is_receptionist(self):
        return self.role == 'receptionist'