"""Deterministic settings used only by pytest."""

from .settings import *  # noqa: F403

ENABLE_SILK = False

INSTALLED_APPS = [
    app for app in INSTALLED_APPS  # noqa: F405
    if app != "silk"
]

MIDDLEWARE = [
    middleware for middleware in MIDDLEWARE  # noqa: F405
    if middleware != "silk.middleware.SilkyMiddleware"
]