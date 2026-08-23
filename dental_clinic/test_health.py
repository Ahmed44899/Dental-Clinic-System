from django.test import Client, override_settings
from django.urls import reverse


def test_health_check_returns_ok(client):
    response = client.get(reverse("health-check"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_check_rejects_unsafe_methods(client):
    response = client.post(reverse("health-check"))

    assert response.status_code == 405


def test_health_check_accepts_load_balancer_private_ip_host():
    with override_settings(ALLOWED_HOSTS=["clinic.example.com"]):
        response = Client().get(
            reverse("health-check"),
            HTTP_HOST="172.31.1.112:8000",
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_other_routes_reject_unapproved_hosts():
    with override_settings(ALLOWED_HOSTS=["clinic.example.com"]):
        response = Client().get(
            "/",
            HTTP_HOST="172.31.1.112:8000",
        )

    assert response.status_code == 400
