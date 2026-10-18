import os
import time
from contextvars import ContextVar

from opentelemetry import metrics

from .telemetry import logger, tracer


EXPERIMENT = "service-b-latency-200ms-v1"
HEADER = "x-lab-chaos-experiment"
STARTED_AT = time.time()
requested_experiment = ContextVar("requested_experiment", default=False)
meter = metrics.get_meter("credit-lab.chaos")
injected_requests = meter.create_counter("chaos.injected.requests", unit="{request}")
injected_delay = meter.create_histogram("chaos.injected.delay", unit="ms")


def enabled():
    try:
        expires = float(os.getenv("CHAOS_EXPIRES_AT", "0"))
    except ValueError:
        return False
    return (
        os.getenv("CHAOS_ENABLED", "false").lower() == "true"
        and time.time() < expires <= STARTED_AT + 1800
    )


class ExperimentContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        token = requested_experiment.set(
            enabled() and headers.get(HEADER.encode()) == EXPERIMENT.encode()
        )
        try:
            await self.app(scope, receive, send)
        finally:
            requested_experiment.reset(token)


def forwarding_headers():
    return {HEADER: EXPERIMENT} if enabled() and requested_experiment.get() else {}


def inject_latency(path):
    if not path.startswith("/credit-applications") or not enabled() or not requested_experiment.get():
        return
    attributes = {"chaos.experiment": EXPERIMENT, "chaos.delay_ms": 200}
    with tracer.start_as_current_span("chaos.latency", attributes=attributes):
        logger.info("chaos.latency.started")
        time.sleep(0.2)
        injected_requests.add(1, {"chaos.experiment": EXPERIMENT})
        injected_delay.record(200, {"chaos.experiment": EXPERIMENT})
        logger.info("chaos.latency.injected")
