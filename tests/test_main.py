import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.service import credit_applications

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_applications():
    credit_applications.clear()


def create_sample_application():
    return client.post(
        "/credit-applications",
        json={
            "customer_name": "Ana Torres",
            "document_number": "1020304050",
            "requested_amount": 15000000,
        },
    )


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics():
    # Make a dummy request to generate HTTP metrics
    client.get("/health")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text or "http_request_duration_seconds" in response.text
    assert "process_cpu_seconds_total" in response.text or "process_resident_memory_bytes" in response.text


def test_create_application_starts_pending():
    response = create_sample_application()
    assert response.status_code == 201
    assert response.json()["application_id"]
    assert response.json()["status"] == "PENDING"


def test_list_applications():
    created = create_sample_application().json()
    response = client.get("/credit-applications")
    assert response.status_code == 200
    assert response.json() == [created]


def test_get_existing_application():
    created = create_sample_application().json()
    response = client.get(f"/credit-applications/{created['application_id']}")
    assert response.status_code == 200
    assert response.json() == created


def test_get_missing_application():
    response = client.get("/credit-applications/missing-id")
    assert response.status_code == 404


def test_update_application_status():
    created = create_sample_application().json()
    response = client.put(
        f"/credit-applications/{created['application_id']}/status",
        json={"status": "APPROVED"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"


def test_invalid_status_is_rejected():
    created = create_sample_application().json()
    response = client.put(
        f"/credit-applications/{created['application_id']}/status",
        json={"status": "UNKNOWN"},
    )
    assert response.status_code == 422
