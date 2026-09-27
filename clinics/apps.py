from django.apps import AppConfig


class ClinicsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'clinics'


from django.contrib.admin.apps import AdminConfig


class PlatformAdminConfig(AdminConfig):
    default_site = 'clinics.admin_support.PlatformAdminSite'
