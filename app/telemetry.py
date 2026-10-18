"""One SDK per process; OTLP traces, metrics and correlated JSON logs."""
import json
import logging
import os
from datetime import datetime, timezone
from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

ENABLED = os.getenv("OTEL_ENABLED", "false").lower() == "true"
SERVICE = os.getenv("OTEL_SERVICE_NAME", "service-a")
tracer = trace.get_tracer("credit-lab")
logger = logging.getLogger("credit-lab")
logger.setLevel(logging.INFO)
logger.propagate = False
providers = []

class JSONFormatter(logging.Formatter):
    def format(self, record):
        ctx = trace.get_current_span().get_span_context()
        return json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname, "service.name": SERVICE,
            "event": record.getMessage(), "trace_id": format(ctx.trace_id, "032x"),
            "span_id": format(ctx.span_id, "016x")})

stream = logging.StreamHandler()
stream.setFormatter(JSONFormatter())
logger.addHandler(stream)

def configure(app, engine=None):
    if not ENABLED:
        return
    resource = Resource.create({"service.name": SERVICE, "deployment.environment": "lab"})
    base = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318").rstrip("/")
    tp = TracerProvider(resource=resource)
    tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=base+"/v1/traces")))
    trace.set_tracer_provider(tp)
    mp = MeterProvider(resource=resource, metric_readers=[PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=base+"/v1/metrics"), export_interval_millis=5000)])
    metrics.set_meter_provider(mp)
    lp = LoggerProvider(resource=resource)
    lp.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=base+"/v1/logs")))
    logger.addHandler(LoggingHandler(level=logging.INFO, logger_provider=lp))
    providers.extend([tp, mp, lp])
    HTTPXClientInstrumentor().instrument()
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
    if engine is not None:
        SQLAlchemyInstrumentor().instrument(engine=engine)
    import psutil
    process = psutil.Process()
    meter = metrics.get_meter("credit-lab")
    meter.create_observable_gauge("credit.process.memory", callbacks=[
        lambda _: [metrics.Observation(process.memory_info().rss)]], unit="By")
    meter.create_observable_counter("credit.process.cpu", callbacks=[
        lambda _: [metrics.Observation(sum(process.cpu_times()[:2]))]], unit="s")

def flush():
    for provider in providers:
        provider.force_flush()
