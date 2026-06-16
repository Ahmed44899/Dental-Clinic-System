from django.contrib import admin
from .models import PatientProfile


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'phone', 'email', 'blood_type', 'created_at']
    list_filter = ['blood_type']
    search_fields = ['full_name', 'phone', 'email']
    ordering = ['full_name']