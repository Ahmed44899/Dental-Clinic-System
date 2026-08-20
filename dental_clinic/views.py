from django.http import JsonResponse
from django.views.decorators.http import require_safe


@require_safe
def health_check(request):
    """Confirm that the Django process is running."""
    return JsonResponse({"status": "ok"})