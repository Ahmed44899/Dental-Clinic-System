import pytest
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor


@pytest.fixture
def nullable_apps(transactional_db):
    """Rehearse pre-constraint data without weakening the current schema."""
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    previous = [
        ('clinics', '0002_assign_existing_clinic'),
        ('patients', '0002_patientprofile_clinic'),
        ('appointments', '0004_appointment_clinic_invoice_clinic_and_more'),
        ('xrays', '0003_xray_clinic'),
    ]
    executor.migrate(previous)
    try:
        with transaction.atomic():
            try:
                yield executor.loader.project_state(previous).apps
            finally:
                transaction.set_rollback(True)
    finally:
        MigrationExecutor(connection).migrate(latest)
