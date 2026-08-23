from .views import health_check


class LoadBalancerHealthCheckMiddleware:
    """Serve health checks before validating the ALB's dynamic Host header."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/health/":
            return health_check(request)

        return self.get_response(request)