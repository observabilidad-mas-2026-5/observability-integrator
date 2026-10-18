from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, Event
from opentelemetry.sdk.trace.export import SpanExportResult

from app.telemetry import SafeSpanExporter


def test_sql_export_excludes_statements_credentials_and_exception_details():
    captured = []

    class Exporter:
        def export(self, spans):
            captured.extend(spans)
            return SpanExportResult.SUCCESS

    span = ReadableSpan(
        name="INSERT credits", attributes={
            "db.system": "postgresql", "db.name": "credits", "db.user": "private-user",
            "db.statement": "INSERT INTO credits VALUES ('personal-data')",
            "db.connection_string": "postgresql://user:password@host/credits",
            "db.query.parameter.name": "personal-data"},
        events=[Event("exception", {"exception.type": "DatabaseError",
                                    "exception.message": "private password",
                                    "exception.stacktrace": "personal-data"})],
        status=trace.Status(trace.StatusCode.ERROR, "private password"))
    assert SafeSpanExporter(Exporter()).export([span]) == SpanExportResult.SUCCESS
    exported = captured[0]
    assert exported.attributes == {
        "db.system": "postgresql", "db.name": "credits", "db.system.name": "postgresql",
        "db.operation.name": "INSERT", "db.namespace": "credits"}
    assert exported.events[0].attributes == {"exception.type": "DatabaseError"}
    assert exported.status.description is None
    assert exported.status.status_code == trace.StatusCode.ERROR
