import time
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app import data_service, error_chaos


TARGET = "c32d2d6c-b73b-4a32-ab55-bbb23da6c616"


def context(sequence, marked=True):
    identifier = (1 << 120) | ((error_chaos.MARKER if marked else 0) | sequence)
    return trace.use_span(trace.NonRecordingSpan(trace.SpanContext(identifier, 1234, False, trace.TraceFlags(1))))


@pytest.fixture
def armed(monkeypatch):
    monkeypatch.setattr(error_chaos, "attempts", 0)
    monkeypatch.setenv("DATA_CHAOS_ENABLED", "true")
    monkeypatch.setenv("DATA_CHAOS_EXPIRES_AT", str(time.time() + 600))
    monkeypatch.setenv("DATA_CHAOS_APPLICATION_ID", TARGET)


@pytest.mark.parametrize("mode", ["default", "disabled", "expired", "invalid", "too-long", "wrong-id", "unmarked", "zero"])
def test_error_injection_fails_closed(monkeypatch, armed, mode):
    if mode == "default":
        monkeypatch.delenv("DATA_CHAOS_ENABLED")
    if mode == "disabled":
        monkeypatch.setenv("DATA_CHAOS_ENABLED", "false")
    if mode == "expired":
        monkeypatch.setenv("DATA_CHAOS_EXPIRES_AT", str(time.time() - 1))
    if mode == "invalid":
        monkeypatch.setenv("DATA_CHAOS_EXPIRES_AT", "invalid")
    if mode == "too-long":
        monkeypatch.setenv("DATA_CHAOS_EXPIRES_AT", str(time.time() + 3600))
    with context(0 if mode == "zero" else 10, marked=mode != "unmarked"):
        error_chaos.inject_error("other" if mode == "wrong-id" else TARGET)


def test_exact_ten_percent_with_correlated_error_spans(monkeypatch, armed):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(error_chaos, "tracer", provider.get_tracer("test"))
    counts = {"eligible": 0, "errors": 0}
    logs = []

    class Counter:
        def __init__(self, key):
            self.key = key

        def add(self, amount, attributes):
            assert attributes == {"chaos.experiment": error_chaos.EXPERIMENT}
            counts[self.key] += amount

    monkeypatch.setattr(error_chaos, "eligible", Counter("eligible"))
    monkeypatch.setattr(error_chaos, "failures", Counter("errors"))
    monkeypatch.setattr(error_chaos.logger, "error", lambda event: logs.append((event, trace.get_current_span().get_span_context().is_valid)))
    failures = []
    for sequence in range(1, 101):
        with context(sequence):
            try:
                error_chaos.inject_error(TARGET)
            except HTTPException as error:
                assert error.status_code == 503
                failures.append(sequence)
    assert failures == list(range(1, 101, 10))
    assert counts == {"eligible": 100, "errors": 10}
    assert logs == [("chaos.error.injected", True)] * 10
    spans = exporter.get_finished_spans()
    assert len(spans) == 10
    assert all(s.name == "chaos.error" and s.status.status_code == trace.StatusCode.ERROR for s in spans)
    assert all(set(s.attributes) == {"chaos.experiment", "chaos.error.rate_percent", "http.status_code"} for s in spans)
    provider.shutdown()


def test_fault_is_before_sql_and_never_affects_health(monkeypatch, armed):
    engine = MagicMock()
    monkeypatch.setattr(data_service, "engine", engine)
    client = TestClient(data_service.app)
    with context(10):
        assert client.get("/credit-applications/" + TARGET).status_code == 503
        engine.connect.assert_not_called()
        assert client.get("/health").status_code == 200
    assert engine.connect.call_count == 1


def test_proxy_retries_do_not_amplify_physical_failure_percentage(armed):
    physical = 0
    errors = 0
    logical_failures = 0
    for sequence in range(1, 451):
        for retry in range(3):
            physical += 1
            with context(sequence):
                try:
                    error_chaos.inject_error(TARGET)
                    break
                except HTTPException:
                    errors += 1
        else:
            logical_failures += 1
    assert physical == 500 and errors == 50 and logical_failures == 0


def test_unmarked_reads_and_404_preserved(monkeypatch, armed):
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.mappings.return_value.first.return_value = None
    monkeypatch.setattr(data_service, "engine", engine)
    with context(10, marked=False):
        assert TestClient(data_service.app).get("/credit-applications/" + TARGET).status_code == 404
    assert engine.connect.call_count == 1
