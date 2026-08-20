from django.urls import reverse


def test_health_check_returns_ok(client):
    response = client.get(reverse("health-check"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_check_rejects_unsafe_methods(client):
    response = client.post(reverse("health-check"))

    assert response.status_code == 405