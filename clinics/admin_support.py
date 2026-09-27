from django.contrib.admin import AdminSite


class PlatformAdminSite(AdminSite):
    def has_permission(self, request):
        return bool(request.user.is_active and request.user.is_staff and request.user.is_superuser)


class ReadOnlyClinicalAdminMixin:
    # Clinical mutations must go through the validated clinic APIs.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
