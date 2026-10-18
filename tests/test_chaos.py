import json
import time
from argparse import Namespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app import chaos, service, storage
from app.main import app
from scripts.chaos_latency import request, run, summarize, validate_url


@pytest.fixture
def armed(monkeypatch):
    monkeypatch.setenv("CHAOS_ENABLED", "true")
    monkeypatch.setenv("CHAOS_EXPIRES_AT", str(time.time() + 600))


@pytest.mark.parametrize("enabled,expiry,marked,path", [
    ("false", 600, True, "/credit-applications"),
    ("true", -1, True, "/credit-applications"),
    ("true", 3600, True, "/credit-applications"),
    ("true", "invalid", True, "/credit-applications"),
    ("true", 600, False, "/credit-applications"),
    ("true", 600, True, "/health"),
    ("true", 600, True, "/metrics"),
])
def test_latency_fails_closed(monkeypatch, enabled, expiry, marked, path):
    monkeypatch.setenv("CHAOS_ENABLED", enabled)
    monkeypatch.setenv("CHAOS_EXPIRES_AT", str(time.time() + expiry) if isinstance(expiry, int) else expiry)
    calls = []
    monkeypatch.setattr(chaos.time, "sleep", calls.append)
    token = chaos.requested_experiment.set(marked)
    try:
        chaos.inject_latency(path)
    finally:
        chaos.requested_experiment.reset(token)
    assert calls == []


def test_latency_default_disabled(monkeypatch):
    monkeypatch.delenv("CHAOS_ENABLED", raising=False)
    monkeypatch.delenv("CHAOS_EXPIRES_AT", raising=False)
    assert not chaos.enabled()
    assert chaos.forwarding_headers() == {}


def test_context_resets_and_contracts_preserved(monkeypatch, armed):
    calls = []
    monkeypatch.setattr(chaos.time, "sleep", calls.append)
    monkeypatch.setattr(storage, "_client", httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"status": "ok"})
    )))
    client = TestClient(storage.app)
    assert client.get("/health", headers={chaos.HEADER: chaos.EXPERIMENT}).status_code == 200
    assert calls == []
    assert not chaos.requested_experiment.get()
    assert client.post("/credit-applications", json={"requested_amount": -1}, headers={chaos.HEADER: chaos.EXPERIMENT}).status_code == 422
    assert calls == []


def test_forwarding_is_opt_in(monkeypatch, armed):
    client = TestClient(app)
    captured = []

    def respond(request):
        captured.append(request.headers.get(chaos.HEADER))
        return httpx.Response(200, json=[])

    monkeypatch.setattr(service, "REMOTE", "http://service-b:8001")
    monkeypatch.setattr(service, "_client", httpx.Client(transport=httpx.MockTransport(respond)))
    assert client.get("/credit-applications", headers={chaos.HEADER: chaos.EXPERIMENT}).status_code == 200
    assert client.get("/credit-applications").status_code == 200
    assert client.get("/credit-applications", headers={chaos.HEADER: "unknown"}).status_code == 200
    assert captured == [chaos.EXPERIMENT, None, None]


def test_statistics_and_empty_window():
    samples = [{"status": 200, "duration_ms": 10}, {"status": 503, "duration_ms": 20}, {"status": 200, "duration_ms": 1100}]
    result = summarize(samples, 0.995, 1000)
    assert result["p99_ms"] == 1100
    assert result["error_rate"] == pytest.approx(1 / 3)
    assert result["slo_bad_requests"] == 2
    assert result["burn_rate"] == pytest.approx((2 / 3) / 0.005)
    assert summarize([], 0.995, 1000)["p99_ms"] is None


@pytest.mark.parametrize("url", ["http://8.8.8.8:8000", "https://localhost:8000", "http://user:password@localhost", "http://localhost/path"])
def test_public_or_credential_urls_rejected(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_transport_failure_is_counted():
    class Opener:
        def open(self, *args, **kwargs):
            raise TimeoutError()

    sample, body = request(Opener(), "GET", "http://localhost:8000/credit-applications/test")
    assert sample["status"] == 0 and body is None


@pytest.mark.parametrize("stdout_only", [False, True])
def test_local_three_phases(monkeypatch, armed, tmp_path, stdout_only):
    rows = {}
    events = []
    writes = []

    def data_response(request):
        if request.method == "POST":
            writes.append(request)
            row = dict(json.loads(request.content), application_id="local-synthetic", status="PENDING")
            rows[row["application_id"]] = row
            return httpx.Response(201, json=row)
        return httpx.Response(200, json=rows["local-synthetic"])

    monkeypatch.setattr(storage, "_client", httpx.Client(transport=httpx.MockTransport(data_response)))
    monkeypatch.setattr(chaos.logger, "info", events.append)
    client_b = TestClient(storage.app)

    def service_b_response(request):
        response = client_b.request(request.method, request.url.path, content=request.content, headers=dict(request.headers))
        return httpx.Response(response.status_code, json=response.json())

    monkeypatch.setattr(service, "REMOTE", "http://service-b:8001")
    monkeypatch.setattr(service, "_client", httpx.Client(transport=httpx.MockTransport(service_b_response)))
    client_a = TestClient(app)

    class Response:
        def __init__(self, response):
            self.response = response
            self.status = response.status_code

        def read(self):
            return self.response.content

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class LocalOpener:
        def open(self, request, timeout):
            return Response(client_a.request(request.method, request.full_url, content=request.data, headers=dict(request.header_items())))

    monkeypatch.setattr("scripts.chaos_latency.urllib.request.build_opener", lambda *args: LocalOpener())
    summary = run(Namespace(base_url="http://localhost:8000", output_dir="-" if stdout_only else str(tmp_path / "run"), environment="local", phase_seconds=0.7, rps=5, slo_target=0.995, latency_slo_ms=1000))
    assert len(writes) == 1
    assert all(phase["error_rate"] == 0 for phase in summary["phases"].values())
    assert summary["phases"]["injection"]["p99_ms"] >= 190
    assert summary["phases"]["injection"]["p99_ms"] > summary["phases"]["baseline"]["p99_ms"] + 100
    assert summary["phases"]["recovery"]["p99_ms"] < summary["phases"]["injection"]["p99_ms"]
    assert events.count("chaos.latency.injected") == summary["phases"]["injection"]["requests"]
    assert summary["mttd_seconds"] is None
    assert (tmp_path / "run").exists() != stdout_only


def test_delay_span_metrics_and_log_context(monkeypatch, armed):
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(chaos, "tracer", provider.get_tracer("chaos-test"))
    sleeps = []
    logs = []
    metrics = []
    monkeypatch.setattr(chaos.time, "sleep", sleeps.append)
    monkeypatch.setattr(chaos.logger, "info", lambda event: logs.append((event, trace.get_current_span().get_span_context().is_valid)))

    class Counter:
        def add(self, value, attributes):
            metrics.append(("counter", value, attributes))

    class Histogram:
        def record(self, value, attributes):
            metrics.append(("histogram", value, attributes))

    monkeypatch.setattr(chaos, "injected_requests", Counter())
    monkeypatch.setattr(chaos, "injected_delay", Histogram())
    token = chaos.requested_experiment.set(True)
    try:
        chaos.inject_latency("/credit-applications/test")
    finally:
        chaos.requested_experiment.reset(token)
        provider.shutdown()
    assert sleeps == [0.2]
    assert logs == [("chaos.latency.started", True), ("chaos.latency.injected", True)]
    assert metrics == [("counter", 1, {"chaos.experiment": chaos.EXPERIMENT}), ("histogram", 200, {"chaos.experiment": chaos.EXPERIMENT})]
    span = exporter.get_finished_spans()[0]
    assert span.name == "chaos.latency"
    assert span.attributes == {"chaos.experiment": chaos.EXPERIMENT, "chaos.delay_ms": 200}
