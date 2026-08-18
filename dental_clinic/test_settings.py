from pathlib import Path

from dental_clinic.settings import BASE_DIR, get_database_config
from dental_clinic import settings_local


DATABASE_ENVIRONMENT_KEYS = (
    'DATABASE_URL',
    'DB_HOST',
    'DB_NAME',
    'DB_USER',
    'DB_PASSWORD',
    'DB_PORT',
)


def clear_database_environment(monkeypatch):
    # Setting an empty environment value also overrides any developer .env
    # file, keeping these tests deterministic on every machine.
    for key in DATABASE_ENVIRONMENT_KEYS:
        monkeypatch.setenv(key, '')


def test_database_url_takes_precedence_over_separate_variables(monkeypatch):
    clear_database_environment(monkeypatch)
    monkeypatch.setenv(
        'DATABASE_URL',
        'postgresql://url_user:url_password@url-db:5432/url_database',
    )
    monkeypatch.setenv('DB_HOST', 'separate-db')

    database = get_database_config()['default']

    assert database['ENGINE'] == 'django.db.backends.postgresql'
    assert database['NAME'] == 'url_database'
    assert database['USER'] == 'url_user'
    assert database['HOST'] == 'url-db'
    assert database['CONN_HEALTH_CHECKS'] is True


def test_separate_database_variables_configure_postgresql(monkeypatch):
    clear_database_environment(monkeypatch)
    monkeypatch.setenv('DB_HOST', 'db')
    monkeypatch.setenv('DB_NAME', 'dental_clinic')
    monkeypatch.setenv('DB_USER', 'clinic_user')
    monkeypatch.setenv('DB_PASSWORD', 'test-only-password')
    monkeypatch.setenv('DB_PORT', '5433')

    database = get_database_config()['default']

    assert database == {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'dental_clinic',
        'USER': 'clinic_user',
        'PASSWORD': 'test-only-password',
        'HOST': 'db',
        'PORT': '5433',
        'CONN_MAX_AGE': 600,
        'CONN_HEALTH_CHECKS': True,
    }


def test_missing_database_configuration_falls_back_to_sqlite(monkeypatch):
    clear_database_environment(monkeypatch)

    database = get_database_config()['default']

    assert database['ENGINE'] == 'django.db.backends.sqlite3'
    assert database['NAME'] == BASE_DIR / 'db.sqlite3'


def test_relative_sqlite_url_is_resolved_from_project_root(monkeypatch):
    clear_database_environment(monkeypatch)
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///temporary.sqlite3')

    database = get_database_config()['default']

    assert database['ENGINE'] == 'django.db.backends.sqlite3'
    assert database['NAME'] == Path(BASE_DIR) / 'temporary.sqlite3'


def test_local_settings_are_isolated_from_hosted_services():
    database = settings_local.DATABASES['default']

    assert database['ENGINE'] == 'django.db.backends.sqlite3'
    assert database['NAME'] == BASE_DIR / 'db.local.sqlite3'
    assert settings_local.XRAY_CLOUD_UPLOAD_ENABLED is False
    assert settings_local.ALLOWED_HOSTS == ['localhost', '127.0.0.1', '[::1]']
