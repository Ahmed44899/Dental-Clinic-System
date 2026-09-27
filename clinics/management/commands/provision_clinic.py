"""Trusted-operator provisioning, not a public signup or invitation endpoint."""
import getpass
import warnings

from django.apps import apps
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.recorder import MigrationRecorder

from clinics.models import Clinic, ClinicMembership
from clinics.ownership import audit_ownership


REQUIRED_MIGRATIONS = {
    ('clinics', '0003_audit_ownership'),
    ('patients', '0003_alter_patientprofile_clinic'),
    ('appointments', '0005_alter_appointment_clinic_alter_invoice_clinic_and_more'),
    ('xrays', '0004_alter_xray_clinic'),
}


class Command(BaseCommand):
    help = 'Interactively create a clinic and a NEW clinic administrator atomically.'
    requires_migrations_checks = True

    def add_arguments(self, parser):
        parser.add_argument('--name', required=True)
        parser.add_argument('--slug', required=True)
        parser.add_argument('--username', required=True)
        parser.add_argument('--email', default='')

    def handle(self, *args, **options):
        applied = MigrationRecorder(connection).applied_migrations()
        if not REQUIRED_MIGRATIONS.issubset(applied):
            raise CommandError('Apply all Phase 4 ownership migrations before creating clinics.')
        if audit_ownership(apps):
            raise CommandError('Ownership audit failed. Run audit_clinic_ownership and resolve its findings.')

        User = get_user_model()
        clinic = Clinic(name=options['name'].strip(), slug=options['slug'].strip())
        user = User(
            username=User.normalize_username(options['username'].strip()),
            email=User.objects.normalize_email(options['email'].strip()),
            role='admin', is_active=True, is_staff=False, is_superuser=False,
        )
        user.set_unusable_password()

        def validate_candidates():
            # Case-insensitive prechecks avoid confusing lookalikes. Database
            # unique constraints remain the final defense for exact duplicates.
            if Clinic.objects.filter(slug__iexact=clinic.slug).exists():
                raise CommandError('Clinic slug already exists; no changes made.')
            if User.objects.filter(username__iexact=user.username).exists():
                raise CommandError('Username already exists. This command never attaches existing accounts.')
            clinic.full_clean()
            user.full_clean()

        try:
            validate_candidates()
            self.stdout.write(f'Create clinic "{clinic.name}" ({clinic.slug}) with NEW admin "{user.username}".')
            self.stdout.write('Target: current Django settings, default database. No AWS or database is selected automatically.')
            if input('Type the clinic slug to confirm: ').strip() != clinic.slug:
                raise CommandError('Confirmation did not match; no changes made.')
            # Never fall back to echoing a password when no secure terminal exists.
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                password = getpass.getpass('New administrator password: ')
                repeated = getpass.getpass('Repeat password: ')
            if password != repeated:
                raise CommandError('Passwords do not match; no changes made.')
            password_validation.validate_password(password, user)
            user.set_password(password)
            with transaction.atomic():
                validate_candidates()
                if audit_ownership(apps):
                    raise CommandError('Ownership changed during provisioning; resolve the audit first.')
                clinic.save(force_insert=True)
                user.save(force_insert=True)
                ClinicMembership.objects.create(
                    clinic=clinic, user=user, role=ClinicMembership.Role.ADMIN, is_active=True,
                )
        except ValidationError as error:
            raise CommandError('; '.join(error.messages)) from error
        except IntegrityError as error:
            raise CommandError('A database constraint prevented provisioning; all writes were rolled back.') from error
        except (EOFError, KeyboardInterrupt, getpass.GetPassWarning) as error:
            raise CommandError('Secure interactive input unavailable or cancelled; no changes made.') from error

        self.stdout.write(self.style.SUCCESS(
            f'Created clinic {clinic.pk} ({clinic.slug}) and administrator user {user.pk}. '
            'No platform-admin privileges granted.'
        ))
