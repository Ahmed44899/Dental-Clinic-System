"""Production settings for AWS deployment.

These settings fail closed when required production configuration is missing.
Local development continues to use settings.py or settings_local.py.
"""

from decouple import config
from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403
from .settings import DATABASES, cloudinary_is_configured


def csv_setting(name):
    """Convert a comma-separated environment variable into a clean list."""
    return [
        value.strip()
        for value in config(name, default="").split(",")
        if value.strip()
    ]


# Production must never expose Django debug information.
DEBUG = False
ENABLE_SILK = False


# Refuse to start with a missing, short, or development secret.
production_secret_key = config("SECRET_KEY", default="").strip()

if (
    len(production_secret_key) < 50
    or production_secret_key.startswith("django-insecure-")
):
    raise ImproperlyConfigured(
        "Production SECRET_KEY must be a random value of at least 50 characters."
    )

SECRET_KEY = production_secret_key


# No development host defaults are allowed in production.
ALLOWED_HOSTS = csv_setting("ALLOWED_HOSTS")

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "ALLOWED_HOSTS must contain the production hostname."
    )

CSRF_TRUSTED_ORIGINS = csv_setting("CSRF_TRUSTED_ORIGINS")


# Production must use PostgreSQL, never the SQLite fallback. The custom backend
# retrieves the current RDS-managed password whenever it opens a connection.
postgresql_engines = {
    "django.db.backends.postgresql",
    "dental_clinic.db_backends.secrets_manager_postgresql",
}

if DATABASES["default"]["ENGINE"] not in postgresql_engines:
    raise ImproperlyConfigured(
        "Production must use PostgreSQL through DATABASE_URL or DB_* settings."
    )

DATABASES["default"].setdefault("OPTIONS", {})
DATABASES["default"]["OPTIONS"].setdefault(
    "sslmode",
    config("DB_SSLMODE", default="require"),
)


# The AWS load balancer terminates HTTPS and tells Django the original protocol.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

HTTPS_ENABLED = config("DJANGO_HTTPS_ENABLED", default=False, cast=bool)

SECURE_SSL_REDIRECT = HTTPS_ENABLED
SESSION_COOKIE_SECURE = HTTPS_ENABLED
CSRF_COOKIE_SECURE = HTTPS_ENABLED

# The ALB checks targets over the VPC's internal HTTP connection. Keep only the
# health endpoint exempt while redirecting every user-facing route to HTTPS.
SECURE_REDIRECT_EXEMPT = [r"^health/$"]

SECURE_HSTS_SECONDS = (
    config("SECURE_HSTS_SECONDS", default=3600, cast=int)
    if HTTPS_ENABLED
    else 0
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = (
    HTTPS_ENABLED
    and config("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False, cast=bool)
)
SECURE_HSTS_PRELOAD = False

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"


# ECS container files are temporary, so every production X-ray needs cloud storage.
if not cloudinary_is_configured:
    raise ImproperlyConfigured(
        "Cloudinary credentials are required for persistent production X-rays."
    )

XRAY_CLOUD_UPLOAD_ENABLED = True


# Send unexpected request failures to the ECS CloudWatch log stream. Values
# from request bodies and environment variables are deliberately not logged.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
