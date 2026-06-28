[API_DOCUMENTATION (1).md](https://github.com/user-attachments/files/29423769/API_DOCUMENTATION.1.md)
# 🦷 Dental Clinic Management System

A Django REST Framework API for managing a dental clinic: staff accounts, patient records, appointments, invoicing, and X-ray imaging — including an automated X-ray import pipeline.

Built by a dentist transitioning into backend development, combining real clinical domain knowledge with DRF best practices: JWT authentication, role-based permissions, signal-driven business logic, custom management commands, and Docker deployment.

## Features

- 🔐 **JWT authentication** with role-based access (dentist / receptionist / admin)
- 🧑‍⚕️ **Patient management** with search and computed fields (e.g. auto-calculated age)
- 📅 **Appointment scheduling** with auto-generated invoices via Django signals
- 💳 **Invoicing** with automatic payment status (unpaid / partial / paid) and validation
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

# Create a .env file (see .env.example)
cp .env.example .env

docker compose build
docker compose up
```

Then, in a separate terminal:

```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Visit `http://localhost:8000/admin/` to confirm it's running.

### Run Tests

```bash
docker compose exec web pytest
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | `True`/`False` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL connection |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | Cloud image storage |

---

## API Reference

Full endpoint documentation, request/response examples, and the auto-import command usage are available in [API_DOCUMENTATION.md](./API_DOCUMENTATION.md).
