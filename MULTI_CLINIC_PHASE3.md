# Phase 3: clinic API isolation

## Request flow

A signed-in client calls /api/accounts/memberships/ to list its active memberships.
It sends X-Clinic-ID on subsequent business API requests. The server looks up
membership each request and rejects inactive users, clinics, or memberships.
A single membership may be selected automatically. Multiple memberships require
a selection; the browser picks its remembered clinic or its first available one
and displays the selection prominently.

Roles come from ClinicMembership, not CustomUser.role or Django is_staff.
Global user role remains for migration compatibility but grants no API authority.
No shared mutable user object or thread-local global stores the selected clinic.

## Read and write boundaries

Patients, appointments, financial records, reports, staff, dentist pickers, X-ray
records and image routes are scoped by the selected clinic. Foreign object IDs
return 404 in detail routes. Foreign relationship inputs fail validation.
Creation assigns clinic ownership on the server, including invoice signals.
Patients and dentists used in booking must belong to the selected clinic.
The existing per-dentist scheduling conflict rule still applies across clinics;
its response does not include other clinics' patient or appointment details.

Staff deactivation now changes one membership. It does not disable a person's
global account or their work in other clinics. Self-deactivation is rejected,
and the last active clinic administrator is protected.

The membership endpoint lists only memberships of the authenticated user.
Creating staff creates a new global account plus one membership atomically.
Existing-account invitations and role editing are not yet offered.

## Other entry points

Django admin requires an active platform superuser with is_staff. Clinical model
pages are read-only, avoiding bypass of appointment, finance and ownership rules.
Platform account management remains available. Creating new clinics and enrolling
existing users currently requires an explicit operator workflow; no public signup
or clinic provisioning endpoint has been added.

X-ray import now requires --clinic ID. It uses patient ID or an exact, unique name
within that clinic. Missing or ambiguous matches are skipped. External image URLs
are still supported for legacy imports; use only trusted private storage.

Switching clinics reloads the frontend so records, dialogs and image blob caches
are discarded. Button visibility depends on the returned membership role.

## Deployment boundary

Changes are local and have not been deployed. Apply all Phase 1/2 migrations
before this application serves requests, otherwise users have no membership.
During rollout, stop legacy writers or use a maintenance window: an old task can
still create NULL clinic rows after the backfill. After all legacy writers stop,
catch up unassigned records, verify relationship ownership, and only then enforce
NOT NULL fields in the next migration phase. Do not onboard a second customer
until these checks and the ownership audit pass.

API isolation does not make raw ORM calls tenant-aware. Shell scripts, bulk
updates, and future background tasks must explicitly supply and validate clinic
ownership. PostgreSQL row-level security is not implemented.

## Local verification

Run pytest with the Compose database and settings_pytest. The suite includes two
clinics with matching patient names and separate financial totals; it exercises
foreign IDs, foreign relations, role changes, membership revocation, image
deletion, import ambiguity, and platform-admin restrictions.
