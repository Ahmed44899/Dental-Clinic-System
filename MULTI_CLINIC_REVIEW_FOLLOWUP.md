# Multi-clinic review follow-up: correctness and query growth

All changes remain local, uncommitted and undeployed.

## Importer correction

The first review found that a malformed X-ray import record could stop the whole
batch. The importer now validates each object, patient identifier, external ID,
timestamp and text field. Each row has its own transaction/savepoint, with known
record-level exceptions caught outside that boundary. A constraint error must
roll back before later rows can safely query the database.

Database outages are not treated as invalid records. Invalid JSON documents fail
before import; bad individual rows count as errors. Dry runs use the same field
validation and track within-batch duplicates. API_DOCUMENTATION.md now documents
the required clinic argument and exact, case-insensitive patient-name matching.

33 new importer tests passed; the full baseline after that correction was 262.

## Membership-query correction

A subsequent CodeRabbit review explicitly included untracked files and identified
a membership query per serialized user (an N+1 query pattern). Nested dentist,
charge-author and payment-recorder serializers were affected as well.

The fix uses Django Prefetch to load only the selected clinic's memberships for
the users present in the response. A clinic-specific to_attr name stores the
batch result on each returned user instance. The serializer reads that result
without another query. Unprefetched single-object and write responses retain a
scoped fallback lookup.

The attribute includes the clinic ID, so even a reused user object cannot reuse
clinic A's membership metadata when serializing for clinic B. An empty cached
list is meaningful: it means no membership in that clinic, not permission to
fall back to the user's global role.

This is response metadata, not an authorization cache. Membership checks still
resolve the authenticated user's access for each request. New requests fetch
fresh memberships, including role changes and deactivation. Inactive memberships
are deliberately retained in metadata so historical ledger attribution and the
administrator's staff directory remain accurate.

Ledger records also batch-load their related user objects with select_related.
Otherwise fixing the membership lookup alone would leave another per-row query
for each charge author or payment recorder.

## Query-growth regression tests

clinics/test_query_counts.py adds 11 tests. Six compare a small response against
one expanded with five more distinct users/records and assert equal query counts.
They also verify roles from the selected clinic, rather than the users' roles in
the other clinic.

| Response | Small fixture | Expanded fixture |
| --- | ---: | ---: |
| Staff directory | 3 | 3 |
| Dentist directory | 3 | 3 |
| Appointments with invoices | 7 | 7 |
| Invoice detail | 6 | 6 |
| Invoice charge list | 8 | 8 |
| Payment list | 8 | 8 |

These counts come from test API requests with forced authentication and are not
production latency benchmarks. JWT authentication or middleware can add queries.
The contract is bounded query growth, not universal equality to these numbers.

Other tests check membership updates on a new request, user-object reuse across
clinics (including an empty prefetch), null ledger actors, and newly registered
staff responses. The targeted suite passed all 11 tests.

Query count is only one aspect of performance. The amount of returned data still
grows with list size; this change does not add pagination or performance limits.

## Verification

- Targeted query-growth suite: 11 passed.
- Full regression suite: **273 passed in 221.55 seconds**.
- Django system check: no issues.
- Migration consistency: no changes detected.
- git diff --check: passed.
- CodeRabbit follow-up with --uncommitted --include-untracked completed and
  raised **0 issues**. Its reported file list includes clinics/querysets.py,
  clinics/test_query_counts.py, the importer regression tests, and the new
  multi-clinic migration and provisioning files.

These results are evidence for this revision, not a guarantee of future behavior
or a substitute for the controlled production rollout. No files were staged or
committed and no production operation was performed during this fix.
