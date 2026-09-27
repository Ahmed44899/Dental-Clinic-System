import json

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.migrations.recorder import MigrationRecorder

from clinics.ownership import audit_ownership


class Command(BaseCommand):
    help = 'Read-only audit of missing or inconsistent clinic ownership.'

    def add_arguments(self, parser):
        parser.add_argument('--database', default='default')

    def handle(self, *args, **options):
        applied = MigrationRecorder(connections[options['database']]).applied_migrations()
        if ('clinics', '0002_assign_existing_clinic') not in applied:
            raise CommandError('Apply the Phase 1 and Phase 2 migrations before running the ownership audit.')
        issues = audit_ownership(apps, options['database'])
        self.stdout.write(json.dumps({'ok': not issues, 'issues': issues}, indent=2))
        if issues:
            raise CommandError('Clinic ownership audit failed. Review the reported records before migrating.')
