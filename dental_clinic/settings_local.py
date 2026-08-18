"""Safe settings for native local development.

This module deliberately ignores any production database or Cloudinary values
loaded by ``settings.py``. Use it through ``manage_local.py`` so local commands
can never connect to the hosted clinical database by accident.
"""

from .settings import *  # noqa: F403


DEBUG = True
ENABLE_SILK = False
SECRET_KEY = 'django-insecure-local-development-only'
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.local.sqlite3',  # noqa: F405
    }
}

# Local development must not upload patient images to an external account.
XRAY_CLOUD_UPLOAD_ENABLED = False
