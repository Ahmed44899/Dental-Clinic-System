from django.db import models
from patients.models import PatientProfile


def xray_upload_path(instance, filename):
    """
    Dynamic upload path — organizes files by patient ID.
    Instead of all xrays dumped in one folder, you get:
    media/xrays/patient_3/scan.jpg
    This is a real-world pattern used in production systems.
    """
    return f'xrays/patient_{instance.patient.id}/{filename}'


class XRay(models.Model):
    STORAGE_CHOICES = [
        ('local', 'Local'),
        ('cloud', 'Cloud'),
        ('both', 'Both'),
    ]
    SOURCE_CHOICES = [
        ('manual', 'Manual Upload'),
        ('auto', 'Auto Import'),
    ]

    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name='xrays')
    appointment = models.ForeignKey(
        'appointments.Appointment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='xrays'
    )
    image_local = models.ImageField(upload_to=xray_upload_path, blank=True)
    image_cloud = models.URLField(blank=True)
    storage_type = models.CharField(max_length=10, choices=STORAGE_CHOICES, default='local')
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='manual')
    external_id = models.CharField(max_length=100, blank=True)  # ID from xray machine
    taken_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-taken_at']
        # unique_together = ('patient', 'external_id')

    def __str__(self):
        return f'XRay of {self.patient} — {self.taken_at}'
    