import json

import pytest
from django.core.exceptions import ImproperlyConfigured

from dental_clinic.db_backends.secrets_manager_postgresql.base import (
    DatabaseWrapper,
    get_secret_credentials,
)


class FakeSecretsClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.secret_ids = []

    def get_secret_value(self, *, SecretId):
        self.secret_ids.append(SecretId)
        return next(self.responses)


def secret_response(username, password):
    return {
        'SecretString': json.dumps({
            'username': username,
            'password': password,
        })
    }


def test_secret_credentials_are_retrieved_again_after_rotation():
    client = FakeSecretsClient([
        secret_response('clinic_admin', 'old-password'),
        secret_response('clinic_admin', 'rotated-password'),
    ])

    first = get_secret_credentials('rds-secret', secrets_client=client)
    second = get_secret_credentials('rds-secret', secrets_client=client)

    assert first == ('clinic_admin', 'old-password')
    assert second == ('clinic_admin', 'rotated-password')
    assert client.secret_ids == ['rds-secret', 'rds-secret']


def test_database_wrapper_replaces_stale_credentials(monkeypatch):
    database_settings = {
        'NAME': 'dental_clinic',
        'USER': 'stale-user',
        'PASSWORD': 'stale-password',
        'HOST': 'private-rds.example',
        'PORT': '5432',
        'OPTIONS': {'rds_secret_arn': 'rds-secret'},
        'AUTOCOMMIT': True,
        'CONN_MAX_AGE': 600,
        'CONN_HEALTH_CHECKS': True,
        'TIME_ZONE': None,
        'TEST': {},
    }
    wrapper = DatabaseWrapper(database_settings, 'default')
    monkeypatch.setattr(
        'dental_clinic.db_backends.secrets_manager_postgresql.base.'
        'get_secret_credentials',
        lambda secret_arn: ('current-user', 'current-password'),
    )

    connection_params = wrapper.get_connection_params()

    assert connection_params['user'] == 'current-user'
    assert connection_params['password'] == 'current-password'
    assert connection_params['host'] == 'private-rds.example'
    assert 'rds_secret_arn' not in connection_params


@pytest.mark.parametrize(
    'response',
    [
        {},
        {'SecretString': 'not-json'},
        {'SecretString': '{}'},
        secret_response('', 'password'),
        secret_response('username', ''),
    ],
)
def test_invalid_secret_fails_closed_without_exposing_values(response):
    client = FakeSecretsClient([response])

    with pytest.raises(ImproperlyConfigured) as error:
        get_secret_credentials('rds-secret', secrets_client=client)

    assert 'test-only-password' not in str(error.value)


def test_aws_failure_does_not_expose_secret_details():
    class FailingClient:
        def get_secret_value(self, *, SecretId):
            raise RuntimeError('sensitive provider detail')

    with pytest.raises(Exception) as error:
        get_secret_credentials('rds-secret', secrets_client=FailingClient())

    assert 'sensitive provider detail' not in str(error.value)
