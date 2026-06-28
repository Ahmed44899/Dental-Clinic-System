#!/bin/sh
python manage.py collectstatic --noinput
python manage.py migrate
gunicorn dental_clinic.wsgi:application --bind 0.0.0.0:$PORT