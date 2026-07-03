#!/bin/sh
set -e

python manage.py collectstatic --noinput
python manage.py migrate

if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    python manage.py shell -c "import os; from django.contrib.auth import get_user_model; User = get_user_model(); username = os.environ['DJANGO_SUPERUSER_USERNAME']; User.objects.filter(username=username).exists() or User.objects.create_superuser(username, os.getenv('DJANGO_SUPERUSER_EMAIL', ''), os.environ['DJANGO_SUPERUSER_PASSWORD'])"
fi

gunicorn dental_clinic.wsgi:application --bind "0.0.0.0:${PORT:-8000}"
