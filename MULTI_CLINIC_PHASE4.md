# Phase 4: ownership audit and mandatory clinic fields

All changes remain local, uncommitted and undeployed.

## Ownership checks

`python manage.py audit_clinic_ownership` is read-only. It emits JSON with
counts and up to 20 record IDs per issue, and exits unsuccessfully on problems.
It requires the Phase 1 and Phase 2 migrations first.

The audit covers all six business models: patients, appointments, invoices,
invoice line items, payment transactions and X-rays. It checks missing clinics,
clinic agreement across every business-record foreign key, X-ray/appointment
patient agreement, and the existence of a dentist membership in each
appointment's clinic. Inactive memberships and subsequent role changes remain
valid historical attribution; booking authorization still requires an active
dentist membership.

The Phase 4 data migration catches up NULL ownership only if exactly the original
`dentomanager-existing` clinic exists. Multiple clinics with unassigned records
cause a failure requiring explicit ownership review. Assigned ownership is never
overwritten. The migration then runs the audit; a failure rolls back its catch-up
on PostgreSQL. It does not create new staff memberships or guess dentist access.

The three schema migrations depend on that audit and make all six clinic fields
NOT NULL, with no default clinic. Client-supplied clinic values cannot assign
ownership: API writers continue to use the validated request membership or parent.

## Writer audit and fix

- Patient creation assigns the request clinic; patient edits cannot change it.
- Booking validates clinic-scoped patient and dentist choices; the invoice signal
  copies the appointment clinic.
- Charges and payments inherit the locked, clinic-scoped invoice's clinic.
- Uploads validate patient and appointment ownership. Imports require an explicit
  active clinic and resolve patients within it.
- Clinical Django admin remains read-only. Staff registration creates a membership
  in the request clinic atomically.

The audit found that appointment patient reassignment could invalidate an existing
X-ray relationship. Appointment updates now refuse that change. Uploads recheck
the appointment after acquiring the same appointment-row lock, so an edit racing
an upload cannot leave different patient IDs on the two records.

NOT NULL enforces presence, not cross-table equality. Raw SQL, bulk ORM changes,
operator scripts and future jobs must still validate ownership. This is not
PostgreSQL row-level security. Run the audit after controlled data operations.

## Rollout order (not executed against production)

1. Back up the database and stop **all** application, import and background writers.
2. Apply migrations through `clinics 0002_assign_existing_clinic` first if needed.
3. Run the read-only audit. Review mismatches; only unassigned records in the
   single original clinic are eligible for automatic Phase 4 catch-up.
4. Apply all remaining migrations, then run the audit again. Keep writers stopped
   throughout: the audit and the three schema migrations are separate transactions.
5. Start the matching application version and verify clinic isolation before
   onboarding another customer clinic.

Reversing the schema migrations restores nullable fields; it does not erase
assigned ownership. Reversing the catch-up marker deliberately preserves data.
Do not resume legacy writers or remove earlier clinic columns as a casual rollback.

## Verification

Use the Compose environment, which explicitly clears hosted database settings:

```text
docker compose run --rm web pytest
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py makemigrations --check --dry-run
docker compose run --rm web python manage.py audit_clinic_ownership
```

Migration tests use historical models and restore the latest schema afterward.
Coverage includes NULL rejection on all six models, each ownership relationship,
missing dentist membership, same-clinic patient mismatch, safe catch-up, ambiguous
ownership refusal, atomic rollback, and the appointment/upload consistency guard.

The existing local Compose application database still predates Phase 1 (its
patient table has no clinic column). It has not been migrated by this work.
The disposable test database is separate from that application database.

Browser verification must use synthetic data in a disposable local database:
login, switch clinics with a shared user, verify patients/visits/finances/X-rays
and staff change together, verify clinic-specific role controls, reload to check
selection persistence, and revoke one membership to check access rejection.
Browser verification results are recorded below when available.

Launch the disposable fixture with:

```text
docker compose run --rm -p 127.0.0.1:8001:8001 web python tools/browser_smoke_server.py
```

Open `http://localhost:8001` and use the temporary credentials printed at startup.
The same user is an administrator in Demo Clinic A and a receptionist in B.
Patient names, visits, synthetic image colors and financial amounts differ by
clinic. The database and media live in the disposable container's temporary
directory; the server never modifies either existing local database.

## Results (2026-09-18)

- Original baseline: 185 passed.
- Expanded full suite: 204 passed, one obsolete nullable-patient test failed
  because the new database constraint correctly rejected its setup.
- After correcting that test to assert rejection: all 79 clinic tests passed,
  including the 20 new Phase 4 tests. No production code changed for that failure.
- Django system checks, migration consistency and `git diff --check` passed.
- Synthetic browser server: all migrations applied, ownership audit clean,
  homepage and health endpoint returned HTTP 200.
- Actual browser interaction remains unverified. The browser tool reported
  `browsers: []` after connection refresh; no callable Composio browser tool was
  exposed in this session, including after the user reported connecting it.

## Follow-up verification (2026-09-18)

The browser connection became available; the earlier browser blocker above is
resolved. Testing used only the disposable synthetic site on localhost:8001.

- The unchanged Phase 4 full suite passed: 205 tests.
- Browser checks confirmed login, switching A/admin to B/receptionist, financial
  totals of USD 100 versus USD 900, clinic-specific dentist filters, Clinic B's
  patient and appointment lists, distinct A/B X-ray cards, a rendered teal B
  image, selection persistence after reload, and logout clearing the clinic UI.
- Admin staff-management and X-ray deletion controls were present in A and absent
  for the receptionist in B. No real patient data or production resources used.
- Browser testing discovered duplicate staff cards for a shared user. Separate
  reverse-relation filters joined different membership rows. The staff query now
  combines clinic and active-membership conditions in one filter, requiring the
  same membership row to satisfy both. Adding distinct() alone would hide the
  duplication without fixing the inactive-local/active-elsewhere condition.
- Two regression cases cover a shared staff member with an active versus inactive
  local membership. The browser confirmed the duplicate disappeared after the
  disposable server was restarted with the fix.
- Final full suite: 207 passed. Django checks, migration consistency, and
  git diff --check passed (Git emitted only line-ending conversion warnings).
- Membership revocation is covered by automated tests, not an interactive browser
  revocation scenario in this run. These are smoke checks, not exhaustive UI QA.

All work remains uncommitted and undeployed. The existing local application
database was not migrated; only automated test databases and the disposable UI
fixture were used. Production rollout still requires the controlled steps above.
