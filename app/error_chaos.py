import os
import time
from threading import Lock

from fastapi import HTTPException
from opentelemetry import metrics, trace

from .telemetry import logger, tracer


EXPERIMENT = "data-service-errors-10pct-v1"
MARKER = 0xE2200000
STARTED_AT = time.time()
meter = metrics.get_meter("credit-lab.chaos")
eligible = meter.create_counter("chaos.error.eligible.requests", unit="{request}")
failures = meter.create_counter("chaos.injected.errors", unit="{request}")
attempt_lock = Lock()
attempts = 0


def inject_error(application_id):
    global attempts
    try:
        expires = float(os.getenv("DATA_CHAOS_EXPIRES_AT", "0"))
    except ValueError:
        return
    context = trace.get_current_span().get_span_context()
    if (
        os.getenv("DATA_CHAOS_ENABLED", "false").lower() != "true"
        or not time.time() < expires <= STARTED_AT + 1800
        or not application_id
        or application_id != os.getenv("DATA_CHAOS_APPLICATION_ID")
        or not context.is_valid
        or context.trace_id & 0xFFFF0000 != MARKER
    ):
        return
    sequence = context.trace_id & 0xFFFF
    if sequence == 0:
        return
    attributes = {"chaos.experiment": EXPERIMENT}
    eligible.add(1, attributes)
    with attempt_lock:
        attempts += 1
        ordinal = attempts
    if (ordinal - 1) % 10:
        return
    with tracer.start_as_current_span("chaos.error", record_exception=False, set_status_on_exception=False) as span:
        span.set_attributes({**attributes, "chaos.error.rate_percent": 10, "http.status_code": 503})
        span.set_status(trace.Status(trace.StatusCode.ERROR))
        failures.add(1, attributes)
        logger.error("chaos.error.injected")
        raise HTTPException(503, "Controlled synthetic data-service failure")
