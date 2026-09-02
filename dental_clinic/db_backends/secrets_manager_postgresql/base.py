import json

import boto3
from django.core.exceptions import ImproperlyConfigured
from django.db.backends.postgresql.base import (
    DatabaseWrapper as PostgreSQLDatabaseWrapper,
)
from django.db.utils import OperationalError


def get_secret_credentials(secret_arn, *, secrets_client=None):
    """Return validated database credentials without caching rotated values."""
    client = secrets_client or boto3.client("secretsmanager")

    try:
        response = client.get_secret_value(SecretId=secret_arn)
    except Exception as error:
        raise OperationalError(
            "Unable to retrieve the current database credentials from "
            "AWS Secrets Manager."
        ) from error

    try:
        secret = json.loads(response["SecretString"])
        username = secret["username"]
        password = secret["password"]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ImproperlyConfigured(
            "The RDS secret must contain non-empty username and password values."
        ) from error

    if not isinstance(username, str) or not username.strip():
        raise ImproperlyConfigured(
            "The RDS secret must contain non-empty username and password values."
        )
    if not isinstance(password, str) or not password:
        raise ImproperlyConfigured(
            "The RDS secret must contain non-empty username and password values."
        )

    return username, password


class DatabaseWrapper(PostgreSQLDatabaseWrapper):
    """Refresh RDS-managed credentials before every new DB connection."""

    def get_connection_params(self):
        connection_params = super().get_connection_params()
        secret_arn = connection_params.pop("rds_secret_arn", "")

        if secret_arn:
            username, password = get_secret_credentials(secret_arn)
            connection_params["user"] = username
            connection_params["password"] = password

        return connection_params
