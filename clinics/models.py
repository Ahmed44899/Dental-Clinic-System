from django.conf import settings
from django.db import models


class Clinic(models.Model):
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ClinicMembership(models.Model):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        DENTIST = 'dentist', 'Dentist'
        RECEPTIONIST = 'receptionist', 'Receptionist'

    clinic = models.ForeignKey(
        Clinic, on_delete=models.PROTECT, related_name='memberships',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='clinic_memberships',
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['clinic', 'user'], name='unique_clinic_user_membership',
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=['admin', 'dentist', 'receptionist']),
                name='clinic_membership_valid_role',
            ),
        ]

    def __str__(self):
        return f'{self.user} at {self.clinic} ({self.role})'
