# Phase 6: disposable migration and recovery rehearsal

## Scope and isolation

This rehearsal used only synthetic data in a separate local Compose project:
dental-clinic-rehearsal-20260927. It did not migrate the normal local application
database, access AWS, create a real clinic, commit changes, or deploy anything.

Files:

- tools/rehearsal.compose.yml: separate PostgreSQL 16 server and application runner.
- tools/rehearse_multiclinic.py: guarded, staged assertions against synthetic data.

The PostgreSQL server has no published ports and uses tmpfs for its data. Its
network is internal and separate from the normal Compose project. The source
mount is read-only. Database and cloud settings are explicitly set to synthetic
values or blank; no env_file imports the real environment. These credentials
are public test fixtures and must never be used for real users or infrastructure.

The Python helper checks its rehearsal marker, settings module, database engine,
host, user, database-name allowlist, and actual database identity. Seeding refuses
a database with any existing tables. It does not automatically clear anything.

This is a local PostgreSQL exercise, not a test of RDS snapshots, IAM permissions,
ECS rollout timing, concurrent production traffic, or an exact RDS minor version.
The observed server was PostgreSQL 16.15; the recorded RDS major version was 16.

## What was exercised

1. Build the old schema from the pre-tenancy migration targets.
2. Seed two synthetic users and one patient, appointment, invoice, line item,
   payment, and X-ray reference.
3. Capture every original concrete field, primary key, and relationship in those
   models as a baseline. The evidence is stored in a rehearsal-only table.
4. Make a pg_dump custom-format backup of that legacy database.
5. Apply the current migrations and compare original fields against the baseline.
   New clinic columns are checked separately; all records belong to the original
   clinic, with corresponding memberships.
6. Run the real provision_clinic command in an interactive terminal. The slug
   confirmation and both hidden password prompts were exercised, not mocked.
7. Log in with real JWTs for both synthetic owners. Create a second-clinic patient
   while deliberately submitting the first clinic's ID; verify the server assigns
   ownership correctly. Check both directions of patient list/detail isolation.
8. Verify that the new clinic cannot see the original appointment, invoice or
   X-ray list; verify the original EGP ledger still totals 250, with 50 paid and
   200 outstanding. Run the ownership audit again.
9. Restore the pre-upgrade backup into a second database and compare every original
   field plus the legacy migration state.

The first preservation check exposed a JSON-decoding issue in the new helper:
raw-cursor JSONB output was text rather than a dict. The helper was corrected;
the migration itself needed no change. Re-running the check then passed.

## Reproduce safely in PowerShell

Run from the authoritative source folder. Do not combine this Compose file with
docker-compose.yml. Use a fresh project name only after checking it is unused.
Run each command separately and stop immediately on any nonzero exit code.

```powershell
$rehearsalArgs = @("-p", "dental-clinic-rehearsal-20260927", "-f", "tools/rehearsal.compose.yml")
docker compose @rehearsalArgs config --quiet
docker compose @rehearsalArgs run --rm --build web python tools/rehearse_multiclinic.py seed
docker compose @rehearsalArgs exec -T rehearsal-db pg_dump -U rehearsal -d clinic_rehearsal --format=custom --file=/tmp/pre-tenancy.dump
docker compose @rehearsalArgs run --rm web python tools/rehearse_multiclinic.py upgrade
docker compose @rehearsalArgs run --rm web python manage.py provision_clinic --name "Synthetic Second Clinic" --slug rehearsal-second --username rehearsal-owner
```

At the confirmation prompt type rehearsal-second. For this disposable exercise
only, enter the synthetic PASSWORD constant from tools/rehearse_multiclinic.py
at both hidden prompts. Do not use a real password here or pass a password as an
argument. This known fixture allows the verification script to perform real login.

```powershell
docker compose @rehearsalArgs run --rm web python tools/rehearse_multiclinic.py verify
docker compose @rehearsalArgs exec -T rehearsal-db createdb -U rehearsal clinic_rehearsal_restore
docker compose @rehearsalArgs exec -T rehearsal-db pg_restore -U rehearsal --dbname=clinic_rehearsal_restore --exit-on-error --no-owner /tmp/pre-tenancy.dump
docker compose @rehearsalArgs run --rm -e DB_NAME=clinic_rehearsal_restore web python tools/rehearse_multiclinic.py verify-legacy
docker compose @rehearsalArgs run --rm web pytest --create-db -p no:cacheprovider
```

The verify stage intentionally writes one synthetic patient; use a fresh rehearsal
for a full repeat rather than rerunning stages blindly. The full suite creates a
separate test database inside this same isolated PostgreSQL server.

## Recovery lesson

A successful backup command is not proof that recovery works. A restore plus
data comparison provides much stronger evidence. Here the restored database was
separate: we did not overwrite the upgraded database or reverse its migrations.

A real pre-upgrade restore can lose writes made after the backup. Production
requires a controlled writer shutdown and an agreed recovery plan. Use the
matching old application version with the restored old schema. Do not casually
point the new code at a pre-tenancy database.

The synthetic X-ray was a database reference, not a real stored image. A database
backup does not back up Cloudinary objects or local image files. Media recovery,
production backup permissions, and an actual RDS restore remain separate work.

## Cleanup

Inspect the exact project before removing it:

```powershell
docker compose @rehearsalArgs ps -a
docker compose @rehearsalArgs down --volumes
```

That cleanup destroys only this disposable project's synthetic databases,
container-local dump, and containers/network. The data is not retained for
recovery, but can be recreated by rerunning the rehearsal. Do not substitute the
normal application project. Downloaded/built images remain cached.

## Results

- Legacy data preservation and ownership assignment: passed.
- Interactive clinic creation with hidden passwords: passed.
- JWT login, clinic isolation, and original ledger checks: passed.
- Restore into a separate database and full original-field comparison: passed.
- Full regression suite on PostgreSQL 16.15: **229 passed in 228.73 seconds**.
- Invalid database-name guard: correctly refused before connection (expected failure).
- Cleanup completed: the disposable container, databases, dump and network were
  removed. The exact project was verified by Compose output and container labels;
  its final container list was empty. The synthetic data can be recreated, not
  recovered from this deleted dump. Docker images remain cached.
- git diff --check passed. No application-code changes were needed in this phase.
- Normal local database and AWS: untouched.
