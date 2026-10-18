import httpx
import pytest
from fastapi.testclient import TestClient

from app import storage


def test_data_service_crud(monkeypatch):
    rows = {}
    calls = []

    def respond(request):
        import json
        calls.append(request)
        path = request.url.path
        if path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.method == "POST":
            row = dict(json.loads(request.content), application_id="test-id", status="PENDING")
            rows["test-id"] = row
            return httpx.Response(201, json=row)
        if path.endswith("/status"):
            rows["test-id"]["status"] = json.loads(request.content)["status"]
            return httpx.Response(200, json=rows["test-id"])
        if path == "/credit-applications":
            return httpx.Response(200, json=list(rows.values()))
        return httpx.Response(200, json=rows["test-id"]) if path.endswith("test-id") else httpx.Response(404)

    monkeypatch.setattr(storage, "_client", httpx.Client(transport=httpx.MockTransport(respond)))
    client = TestClient(storage.app)
    assert client.get("/health").json() == {"status": "ok"}
    response = client.post("/credit-applications", json={
        "customer_name": "Synthetic", "document_number": "TEST", "requested_amount": 100})
    assert response.status_code == 201
    row = response.json()
    assert row["status"] == "PENDING"
    assert client.get("/credit-applications").json() == [row]
    assert client.get("/credit-applications/test-id").json() == row
    assert client.put("/credit-applications/test-id/status", json={"status": "APPROVED"}).json()["status"] == "APPROVED"
    assert client.get("/credit-applications/missing").status_code == 404
    call_count = len(calls)
    assert client.post("/credit-applications", json={"requested_amount": -1}).status_code == 422
    assert client.put("/credit-applications/test-id/status", json={"status": "INVALID"}).status_code == 422
    assert len(calls) == call_count
    assert all(str(request.url).startswith(storage.DATA_SERVICE_URL) for request in calls)


@pytest.mark.parametrize("failure", ["connection", "timeout", "503", "500"])
def test_data_service_unavailable(monkeypatch, failure):
    def respond(request):
        if failure == "connection":
            raise httpx.ConnectError("unavailable", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(int(failure))

    monkeypatch.setattr(storage, "_client", httpx.Client(transport=httpx.MockTransport(respond)))
    response = TestClient(storage.app).get("/credit-applications")
    assert response.status_code == 503
    assert response.json() == {"detail": "Credit storage unavailable"}
