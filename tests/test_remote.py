import httpx
from fastapi.testclient import TestClient
from app.main import app
from app import service

def test_remote_crud_and_validation(monkeypatch):
    rows = {}
    def respond(req):
        path = req.url.path
        if req.method == "POST":
            import json
            row = dict(json.loads(req.content), application_id="synthetic-id", status="PENDING")
            rows[row["application_id"]] = row
            return httpx.Response(201, json=row)
        if path.endswith("/status"):
            rows["synthetic-id"]["status"] = "APPROVED"
            return httpx.Response(200, json=rows["synthetic-id"])
        if path == "/credit-applications":
            return httpx.Response(200, json=list(rows.values()))
        return httpx.Response(200, json=rows[path.split("/")[-1]]) if path.split("/")[-1] in rows else httpx.Response(404)
    monkeypatch.setattr(service, "REMOTE", "http://storage")
    monkeypatch.setattr(service, "_client", httpx.Client(transport=httpx.MockTransport(respond)))
    client = TestClient(app)
    row=client.post('/credit-applications',json={'customer_name':'Test','document_number':'TEST','requested_amount':1}).json()
    assert row['status']=='PENDING'
    assert client.get('/credit-applications').json()==[row]
    assert client.get('/credit-applications/synthetic-id').json()==row
    assert client.put('/credit-applications/synthetic-id/status',json={'status':'APPROVED'}).json()['status']=='APPROVED'
    assert client.get('/credit-applications/missing').status_code==404
    assert client.post('/credit-applications',json={'requested_amount':-1}).status_code==422

def test_storage_unavailable_is_503(monkeypatch):
    def fail(req):
        raise httpx.ConnectError("unavailable", request=req)
    monkeypatch.setattr(service, "REMOTE", "http://storage")
    monkeypatch.setattr(service, "_client", httpx.Client(transport=httpx.MockTransport(fail)))
    assert TestClient(app).get('/credit-applications').status_code==503
