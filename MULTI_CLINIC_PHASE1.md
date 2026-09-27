# Multi-clinic migration: Phase 1

This phase adds schema only. It does not provide clinic isolation.
Keep production limited to the existing single clinic until the access-control
and backfill phases have been implemented and verified.

## What was added

- Clinic: name, unique slug, active flag, creation timestamp.
- ClinicMembership: user, clinic, role, active flag, creation timestamp.
- A database uniqueness constraint on (clinic, user), including inactive memberships.
- A database constraint limiting roles to admin, dentist, receptionist.
- Optional clinic foreign keys on PatientProfile, Appointment, Invoice,
  InvoiceLineItem, PaymentTransaction, and XRay.

A user can have different roles in different clinics. The existing CustomUser.role
continues to control application behavior in this phase. Membership roles are not
used for authorization yet.

Clinic references use PROTECT so deleting a clinic cannot silently remove its
patients or financial history. Membership user references also use PROTECT;
deactivation is preferable to deleting staff history.

## Why nullable fields come first

Existing rows have no clinic. Adding a required column immediately would require
a default or data rewrite. These migrations leave existing ownership NULL and
preserve IDs, relationships, money amounts, and storage references.

New records also remain unassigned under the current application. A one-time
backfill alone is insufficient while older code can still create unassigned rows.
The next phases must cover all writers, backfill existing data, then perform a
final catch-up and verify zero NULL or inconsistent ownership before adding
NOT NULL constraints.

No Clinic or membership is automatically created in Phase 1. There is no tenant
selector, role conversion, admin registration, or change to API response fields.
No production migration is performed by this implementation.

## Verification

Run from the authoritative project folder:

    docker compose run --rm -e DB_SECRET_ARN= web pytest clinics/tests.py
    docker compose run --rm -e DB_SECRET_ARN= web pytest
    docker compose run --rm -e DB_SECRET_ARN= web python manage.py check
    docker compose run --rm -e DB_SECRET_ARN= web python manage.py makemigrations --check --dry-run

Tests rehearse an upgrade from the previous schema and check that patient,
appointment, invoice, charge, payment, and X-ray records survive with unchanged
business data. This happens in the disposable test database.

## Next phase

Create the existing clinic and memberships with a historical-model data migration;
introduce server-validated active clinic context and clinic-aware writers/readers.
Separate platform privileges from clinic roles. Validate linked records belong to
the same clinic, including admin, imports, invoice signals, and financial reports.
Nullable foreign keys alone do not enforce any of these rules.

Decide explicitly how a dentist working in two clinics should handle conflicting
appointment times. The existing per-dentist scheduling constraint is preserved.

Do not enable a second customer clinic until authorization and two-clinic
isolation tests cover every read/write path. Later migration reversal would remove
ownership metadata, so use a reviewed rollback plan once clinic data exists.
