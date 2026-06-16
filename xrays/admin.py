from django.contrib import admin
from .models import XRay


@admin.register(XRay)
class XRayAdmin(admin.ModelAdmin):
    list_display = ['patient', 'taken_at', 'storage_type', 'source', 'imported_at']
    list_filter = ['storage_type', 'source']
    search_fields = ['patient__full_name', 'description', 'external_id']