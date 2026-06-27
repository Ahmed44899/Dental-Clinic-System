# Dental Clinic API — Documentation

A Django REST Framework API for managing a dental clinic: staff accounts, patient records, appointments, invoicing, and X-ray imaging — including an automated X-ray import pipeline.

Built by a dentist transitioning into backend development, combining real clinical domain knowledge with DRF best practices (JWT auth, role-based permissions, signals, management commands, Docker).

---

## Base URL

```
Local:      http://localhost:8000
Codespaces: https://<your-codespace-name>-8000.app.github.dev
```

All endpoints are prefixed with `/api/`.

---

## Authentication

This API uses **JWT (JSON Web Token)** authentication via `djangorestframework-simplejwt`.

Every endpoint except `/api/accounts/login/` and `/api/accounts/token/refresh/` requires a valid access token sent as:

```
Authorization: Bearer <access_token>
```

Access tokens expire after a short period — use the refresh endpoint to get a new one without logging in again.

### POST `/api/accounts/login/`

Authenticate and receive a token pair.

**Request body**
```json
{
    "username": "ahmed",
    "password": "your_password"
}
```

**Response — 200 OK**
```json
{
    "access": "eyJhbGciOiJIUzI1NiIs...",
    "refresh": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Response — 401 Unauthorized** (wrong credentials)
```json
{
    "detail": "No active account found with the given credentials"
}
```

---

### POST `/api/accounts/token/refresh/`

Exchange a refresh token for a new access token.

**Request body**
```json
{
    "refresh": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Response — 200 OK**
```json
{
    "access": "eyJhbGciOiJIUzI1NiIs..."
}
```

---

## Roles

| Role | Description |
|------|-------------|
| `dentist` | Can be assigned to appointments. Has a `specialization` and `license_number`. |
| `receptionist` | Default role. Manages patients, appointments, and payments. |
| `admin` | Can register new staff accounts (`is_staff=True` required). |

This is a **staff-only system** — patients do not have login accounts.

---

## Accounts

### POST `/api/accounts/register/` 🔒 Admin only

Create a new staff account (dentist, receptionist, or admin).

**Request body**
```json
{
    "username": "newdentist",
    "email": "newdentist@clinic.com",
    "password": "securepass123",
    "role": "dentist",
    "specialization": "Orthodontics",
    "license_number": "LIC00123"
}
```

**Response — 201 Created**
```json
{
    "id": 5,
    "username": "newdentist",
    "email": "newdentist@clinic.com",
    "first_name": "",
    "last_name": "",
    "role": "dentist",
    "phone": "",
    "specialization": "Orthodontics",
    "license_number": "LIC00123"
}
```
> Note: `password` is never returned in any response.

**Response — 403 Forbidden** (non-admin attempting to register staff)

---

### GET `/api/accounts/staff/` 🔒 Auth required

List all staff members (any role).

**Response — 200 OK**
```json
[
    {
        "id": 1,
        "username": "ahmed",
        "role": "admin",
        ...
    },
    {
        "id": 2,
        "username": "dr_mohamed",
        "role": "dentist",
        "specialization": "Orthodontics",
        ...
    }
]
```

---

### GET `/api/accounts/dentists/` 🔒 Auth required

List only users with `role=dentist`. Used when assigning a dentist to an appointment.

**Query params**
| Param | Description |
|-------|-------------|
| `search` | Filter by first name, last name, or specialization |

**Example**
```
GET /api/accounts/dentists/?search=ortho
```

---

## Patients

Patients are records only — they do not log in.

### GET `/api/patients/` 🔒 Auth required

List all patients.

**Query params**
| Param | Description |
|-------|-------------|
| `search` | Search by `full_name`, `phone`, or `email` |
| `ordering` | Order by `full_name` or `created_at` (prefix `-` for descending) |

---

### GET `/api/patients/search/` 🔒 Auth required

Lightweight endpoint for finding a patient before booking an appointment. Returns only `id`, `full_name`, `phone`, `date_of_birth`.

```
GET /api/patients/search/?search=ahmed
```

**Response — 200 OK**
```json
[
    { "id": 3, "full_name": "Ahmed Ali", "phone": "01012345678", "date_of_birth": "1990-05-15" }
]
```

---

### POST `/api/patients/` 🔒 Auth required

**Request body**
```json
{
    "full_name": "Ahmed Hassan",
    "phone": "01012345678",
    "email": "ahmed.h@email.com",
    "date_of_birth": "1990-05-15",
    "blood_type": "A+",
    "allergies": "",
    "medical_notes": ""
}
```

**Response — 201 Created** — includes a computed `age` field (not stored, calculated from `date_of_birth`):
```json
{
    "id": 3,
    "full_name": "Ahmed Hassan",
    "age": 36,
    "phone": "01012345678",
    "email": "ahmed.h@email.com",
    "date_of_birth": "1990-05-15",
    "blood_type": "A+",
    "allergies": "",
    "medical_notes": "",
    "created_at": "2026-06-01T10:00:00Z",
    "updated_at": "2026-06-01T10:00:00Z"
}
```

**Response — 400 Bad Request** (invalid phone format)
```json
{ "phone": ["Phone number must contain only digits, +, or -."] }
```

---

### GET / PATCH / DELETE `/api/patients/<id>/` 🔒 Auth required

Standard retrieve, partial update, and delete for a single patient.

---

## Appointments

The central model of the system. Creating an appointment **automatically creates an Invoice** via a Django signal — you never create invoices manually.

### GET `/api/appointments/` 🔒 Auth required

**Query params**
| Param | Description |
|-------|-------------|
| `status` | Filter: `scheduled`, `completed`, `cancelled`, `no_show` |
| `dentist` | Filter by dentist user ID |
| `patient` | Filter by patient ID |
| `search` | Search by patient name, dentist name, or chief complaint |
| `ordering` | `date_time` or `created_at` |

---

### POST `/api/appointments/` 🔒 Auth required

**Request body**
```json
{
    "patient": 3,
    "dentist": 2,
    "date_time": "2026-07-01T15:00:00Z",
    "chief_complaint": "Toothache",
    "diagnosis": "",
    "procedures_done": "",
    "notes": ""
}
```

**Response — 201 Created**
```json
{
    "id": 10,
    "patient": 3,
    "patient_detail": { "id": 3, "full_name": "Ahmed Hassan", ... },
    "dentist": 2,
    "dentist_detail": { "id": 2, "username": "dr_mohamed", "specialization": "Orthodontics", ... },
    "date_time": "2026-07-01T15:00:00Z",
    "chief_complaint": "Toothache",
    "status": "scheduled",
    "invoice": {
        "id": 10,
        "total_fees": "0.00",
        "amount_paid": "0.00",
        "balance": "0.00",
        "status": "unpaid",
        "payment_method": "cash"
    },
    "created_at": "2026-06-28T12:00:00Z",
    "updated_at": "2026-06-28T12:00:00Z"
}
```

**Validation rules**
- `date_time` cannot be in the past → `400 Bad Request` if violated
- `dentist` must be a user with `role=dentist` — a receptionist or admin ID will be rejected with `400 Bad Request`

---

### GET / PATCH / DELETE `/api/appointments/<id>/` 🔒 Auth required

Retrieve, update, or delete a single appointment (includes nested invoice).

---

### GET / PATCH `/api/appointments/<id>/invoice/` 🔒 Auth required

Record or update a payment for an appointment. **No create or delete** — the invoice is always auto-created by the signal when the appointment is created, and financial records are never deleted.

**Request body**
```json
{
    "total_fees": "500.00",
    "amount_paid": "300.00",
    "payment_method": "cash"
}
```

**Response — 200 OK** — `status` and `balance` are computed automatically:
```json
{
    "id": 10,
    "total_fees": "500.00",
    "amount_paid": "300.00",
    "balance": "200.00",
    "payment_method": "cash",
    "status": "partial"
}
```

| `amount_paid` vs `total_fees` | Resulting `status` |
|---|---|
| `0` | `unpaid` |
| `0 < paid < total` | `partial` |
| `paid == total` | `paid` |

**Response — 400 Bad Request** (overpayment)
```json
{ "non_field_errors": ["Amount paid cannot exceed total fees."] }
```

---

## X-Rays

Supports manual upload (with dual local + cloud storage) and automated import from an external system.

### POST `/api/xrays/` 🔒 Auth required

Upload an X-ray image for a patient. Must use `multipart/form-data` — **not** raw JSON — because of the file upload.

**Form-data fields**
| Field | Type | Required |
|-------|------|----------|
| `patient` | integer (patient ID) | Yes |
| `image_file` | file | Yes |
| `description` | text | No |

**Response — 201 Created**
```json
{
    "id": 7,
    "patient": 3,
    "appointment": null,
    "image_local": "/media/xrays/patient_3/scan.jpg",
    "image_cloud": "https://res.cloudinary.com/.../scan.jpg",
    "storage_type": "both",
    "source": "manual",
    "external_id": "",
    "taken_at": null,
    "description": "Upper molar scan",
    "imported_at": "2026-06-28T12:00:00Z"
}
```
> The image is saved locally first; if Cloudinary upload succeeds, `storage_type` becomes `both`. If Cloudinary fails, the local copy is preserved and the upload still succeeds.

---

### GET `/api/xrays/?patient=<id>` 🔒 Auth required

List all X-rays for a specific patient — a patient's full imaging history in one call.

---

### GET `/api/xrays/<id>/` 🔒 Auth required
### DELETE `/api/xrays/<id>/` 🔒 Auth required

X-ray records support retrieve and delete only — **no update**, by design. An X-ray record shouldn't be edited after creation; if it's wrong, delete and re-upload.

**Response — 405 Method Not Allowed** if `PATCH`/`PUT` is attempted.

---

## Automated X-Ray Import

A custom Django management command imports X-rays in bulk from an external JSON source (e.g. an X-ray machine's export, or a legacy system), matching them to existing patients by name.

```bash
python manage.py import_xrays --source xray_data.json
```

**Options**
| Flag | Description |
|------|-------------|
| `--source` | Path to the JSON file (default: `xray_data.json`) |
| `--dry-run` | Preview the import without saving anything |

**Expected JSON format**
```json
[
    {
        "xray_id": "XR001",
        "patient_name": "Ahmed Ali",
        "image_url": "https://example.com/xray1.jpg",
        "taken_at": "2024-01-15T10:30:00Z",
        "description": "Upper molar periapical"
    }
]
```

**Behavior**
- Matches patients by case-insensitive partial name match (`full_name__icontains`)
- Skips a record if that `external_id` already exists for the matched patient
- Reports unmatched patients as errors without stopping the rest of the import
- `--dry-run` previews exactly what would happen with zero database writes

**Sample output**
```
  Imported xray for Ahmed Ali
Patient not found: NonexistentPatient

Done — Imported: 1 | Skipped: 0 | Errors: 1
```

---

## Error Format

All validation errors follow DRF's standard format — field name mapped to a list of error messages:

```json
{
    "field_name": ["Error message here."]
}
```

Non-field errors (e.g. business logic failures spanning multiple fields) use:

```json
{
    "non_field_errors": ["Error message here."]
}
```

Authentication errors:
```json
{ "detail": "Authentication credentials were not provided." }
```

---

## Tech Stack

- **Django 4.2** + **Django REST Framework**
- **PostgreSQL** (production/Docker), SQLite (local dev fallback)
- **JWT auth** via `djangorestframework-simplejwt`
- **django-filter** for query filtering
- **Cloudinary** for cloud image storage
- **Docker + docker-compose** for containerized deployment
- **pytest + factory_boy + Faker** for testing
- Django **signals** for auto-invoice creation
- Custom **management command** for automated X-ray import

---

## Testing

```bash
docker compose exec web pytest
```

The test suite covers:
- JWT auth (login, registration, role-based permissions)
- Patient CRUD, search, and validation
- Appointment creation, signal-triggered invoicing, and payment status logic
- X-ray upload, filtering, and method restrictions
- The `import_xrays` management command (matching, skipping, dry-run, error handling)
