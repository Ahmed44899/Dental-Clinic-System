# Phase 2: existing-clinic backfill and membership resolution

The new data migration creates DentoManager Clinic (slug dentomanager-existing),
assigns the six business models' unassigned rows, and creates memberships for
existing users. It preserves record IDs, amounts, relationships, and file references.

Legacy staff/superusers receive an admin membership only in this existing clinic,
matching the old permission helper. Other users retain their existing role.
Inactive accounts receive inactive memberships. Existing memberships are preserved
if the migration is retried. No future user or clinic automatically receives access.

The migration rejects a database containing other clinics rather than guessing
ownership. It rejects unsupported user roles before writing. Django runs it
atomically on PostgreSQL. Reversing its migration marker is a no-op: it deliberately
retains ownership and memberships to avoid destroying later edits. This is not a
data rollback; take a backup and review rollback requirements before deployment.

clinics/access.py resolves an active membership after authentication. With exactly
one active clinic it selects that clinic; with multiple clinics it requires an
explicit selection. A clinic ID is only a request, never proof of permission.
Every lookup checks active user, membership, and clinic state in the database.
Platform staff/superuser flags grant no bypass in this helper.

This helper is not wired into the current API yet. Existing endpoints continue
using the legacy permissions, and current writers can still create NULL ownership.
Do not enable a second customer clinic. The next implementation must wire clinic
context through APIs, writers, reports, imports, admin, and the frontend together.
Then backfill any remaining rows, verify ownership consistency, and require clinic
fields at the database level.

Verification uses disposable test databases only. No production changes are made.
