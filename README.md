[API_DOCUMENTATION (1).md](https://github.com/user-attachments/files/29423769/API_DOCUMENTATION.1.md)
# 🦷 Dental Clinic Management System

A Django REST Framework API for managing a dental clinic: staff accounts, patient records, appointments, invoicing, and X-ray imaging — including an automated X-ray import pipeline.

Built by a dentist transitioning into backend development, combining real clinical domain knowledge with DRF best practices: JWT authentication, role-based permissions, signal-driven business logic, custom management commands, and Docker deployment.

## Features

- 🔐 **JWT authentication** with role-based access (dentist / receptionist / admin)
- 🧑‍⚕️ **Patient management** with search and computed fields (e.g. auto-calculated age)
- 📅 **Appointment scheduling** with auto-generated invoices via Django signals
- 💳 **Financial ledger** with USD/EGP invoices, treatment lines, immutable payments/refunds, receivables, and date/month/dentist reporting
- 🩻 **X-ray management** with dual local + cloud (Cloudinary) storage
- 🤖 **Automated X-ray import** from an external JSON source via a custom management command
- ✅ Fully tested with `pytest` + `factory_boy` (signals, permissions, validation, edge cases)
- 🐳 **Dockerized** with PostgreSQL via `docker-compose`

## Tech Stack

- **Django 4.2** + **Django REST Framework**
- **PostgreSQL** (Docker), SQLite (local fallback)
- **JWT auth** via `djangorestframework-simplejwt`
- **django-filter**, **Cloudinary**, **Pillow**
- **Docker + docker-compose**
- **pytest**, **factory_boy**, **Faker**

## Project Structure

```
dental_clinic/
├── accounts/       # Custom user model, roles, JWT auth
├── patients/       # Patient profiles, search
├── appointments/   # Appointments, invoices, signals
├── xrays/          # X-ray uploads, auto-import command
└── dental_clinic/  # Project settings, URLs
```

## Setup & Installation

### Run with Docker (recommended)

```bash
git clone <your-repo-url>
cd dental-clinic-system

# Create a private local configuration from the safe template
cp .env.example .env

docker compose up --build
```

The web container waits for PostgreSQL, runs migrations, collects static files,
and then starts Gunicorn. To create an administrator, use a separate terminal:

```bash
docker compose exec web python manage.py createsuperuser
```

Visit `http://localhost:8000/admin/` to confirm it's running.

Docker Compose explicitly ignores `DATABASE_URL` from `.env` and connects to
its own PostgreSQL container. This prevents local migrations from reaching a
hosted production database accidentally.

### Run natively with Python or Ubuntu

Do not use ordinary `python manage.py ...` commands when your `.env` contains
online credentials. Use the local command runner instead:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python manage_local.py migrate
python manage_local.py createsuperuser
python manage_local.py runserver
```

Then open `http://127.0.0.1:8000/`.

`manage_local.py` always selects `dental_clinic.settings_local`, which uses the
ignored file `db.local.sqlite3`, disables external X-ray uploads, and cannot be
redirected to the online database by values in `.env`. The normal `manage.py`
remains available for deliberate production and deployment commands.

### Run Tests

```bash
docker compose run --rm web pytest
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | `True`/`False` |
| `DATABASE_URL` | Optional database URL used by hosting platforms; takes precedence over `DB_*` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL connection used by Docker Compose |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | Cloud image storage |

For safe native development, use `manage_local.py`; it always uses an isolated
SQLite database regardless of the database values in `.env`. Docker Compose
uses its own local PostgreSQL service. Never use SQLite in production.

---

## API Reference

Full endpoint documentation, request/response examples, and the auto-import command usage are available in [API_DOCUMENTATION.md](./API_DOCUMENTATION.md).
