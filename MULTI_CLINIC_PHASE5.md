# Phase 5: controlled clinic provisioning

Status: local implementation only. No real clinic has been provisioned, no
application database migrated, no deployment or Git commit made by this phase.

## What this adds

The trusted platform operator can create a clinic and its first administrator:

```powershell
docker compose run --rm web python manage.py provision_clinic --name "Example Dental" --slug example-dental --username example-owner --email owner@example.test
```

This is a usage example, not a command that was executed. It requires the Phase 4
migrations on the target database first. Do not migrate production just to try it.
Follow the backup, writer shutdown, audit, and rollout steps in
MULTI_CLINIC_PHASE4.md. The existing local application database may also need
that migration rehearsal. Tests use a separate test database.

Run from the authoritative source folder:
C:\Users\Shata\Desktop\Dental clinic claude\dental_clinic

The command shows the proposed name, slug, and username, asks you to type the slug
to confirm, then asks for the password twice with hidden input. Use a terminal
with secure interactive input; the command refuses getpass's visible-input
fallback. There is no --password option or unattended bypass. Do not put a
password in shell history, Git, screenshots, or learning notes.

The command uses the default database from the active Django settings; it does
not select AWS, discover a target environment, or switch to a safe database
automatically. The checked-in Compose configuration explicitly clears hosted
database settings and targets the local db service. Outside Compose, verify
your environment before running it. On production, only a trusted operator
with narrowly controlled application-shell access should run it.

## Why these decisions matter

### Clinic administrator is not platform administrator

The new account has an active admin membership in the new clinic, but
is_staff=False and is_superuser=False. It cannot enter platform Django admin or
access another clinic just because it administers its own clinic. The old
CustomUser.role is set to admin for compatibility; request authorization must
continue to use ClinicMembership, not that global field.

A new clinic is a database row, not another Docker container or AWS service.
The shared application selects data through the authenticated membership.

### New users only

The command refuses an existing username, including case-insensitive matches.
It never resets an existing password, adds an existing user to a clinic, or
changes existing memberships. Likewise it refuses an existing clinic slug.
Retries fail safely rather than silently modifying the first result.

Email is optional contact information. It is not verified, unique identity,
or an invitation. No email is sent. Secure credential handoff is still an
operator responsibility. Existing-user invitations and self-service signup
require a separate explicit workflow; they are not implemented here.

### Validate before saving

The command checks all four Phase 4 migration markers and runs the read-only
ownership audit. It validates model fields, checks duplicates, and applies the
project's configured Django password validators.

It rechecks candidates and ownership immediately before writing. The migration
gate and audit are deployment safeguards, not substitutes for maintenance-mode
rollout. They do not lock all business writers or establish database row-level
security. Case-insensitive duplicate checks are usability guards; the current
database uniqueness constraints enforce exact duplicates.

### All-or-nothing transaction

Clinic, user, and admin membership are saved inside transaction.atomic().
A failure while creating the membership rolls back the clinic and account too.
That avoids a half-created clinic with no administrator. Tests deliberately
simulate this failure and confirm that the record counts do not change.

Passwords are hashed with set_password(), never saved or printed as plaintext.
The command does not display the password on success.

## Testing

Verified on 2026-09-27: full suite **229 passed in 234.71 seconds**; Django
system checks clean; makemigrations --check --dry-run reported no changes;
git diff --check passed.

Targeted provisioning suite: 22 passed. It covers:

- creation, hashed passwords, login, empty patient list, and clinic role;
- invalid names, slugs, usernames, and email;
- existing identities and safe retries;
- incorrect confirmation, weak/mismatched passwords, interrupted input;
- refusing missing migrations and failing ownership audits;
- atomic rollback and denial of another clinic's API.

The hidden prompts are mocked in automated tests; an end-to-end human terminal
prompt rehearsal is not claimed. Do that against a disposable/local migrated
database before production use. No new schema migration is expected.

## What remains

- Commit and review the accumulated multi-clinic changes.
- Rehearse the production migration and backup/restore procedure before rollout.
- Keep a separate decision point for deploying or onboarding a real customer.
- Add invitations/password setup, onboarding audit events, and self-service
  registration only as deliberately designed later features.
