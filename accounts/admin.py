from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

# Extends the default UserAdmin to include your custom fields
@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'role', 'is_active']
    list_filter = ['role']
    fieldsets = UserAdmin.fieldsets + (
        ('Clinic Info', {'fields': ('role', 'phone', 'specialization', 'license_number')}),
    )