import psutil
from fastapi import FastAPI, HTTPException
from prometheus_client import REGISTRY
from prometheus_client.core import GaugeMetricFamily
from prometheus_fastapi_instrumentator import Instrumentator

from .models import (
    CreditApplication,
    CreditApplicationCreate,
    CreditApplicationStatusUpdate,
)
from .service import (
    create_credit_application,
    get_credit_application,
    list_credit_applications,
    update_credit_application_status,
)


class SystemMetricsCollector:
    def collect(self):
        process = psutil.Process()

        cpu = GaugeMetricFamily(
            "process_cpu_seconds_total",
            "Total user and system CPU time spent in seconds.",
        )
        cpu.add_sample(
            "process_cpu_seconds_total",
            value=process.cpu_times().user + process.cpu_times().system,
            labels={},
        )
        yield cpu

        mem = GaugeMetricFamily(
            "process_resident_memory_bytes",
            "Resident memory size in bytes.",
        )
        mem.add_sample(
            "process_resident_memory_bytes",
            value=process.memory_info().rss,
            labels={},
        )
        yield mem


try:
    REGISTRY.register(SystemMetricsCollector())
except Exception:
    pass

app = FastAPI(title="DevOps Bank Credit Application API")

from .telemetry import configure
configure(app)

Instrumentator().instrument(app).expose(app)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post(
    "/credit-applications", response_model=CreditApplication, status_code=201
)
def create_application(data: CreditApplicationCreate):
    return create_credit_application(data)


@app.get("/credit-applications", response_model=list[CreditApplication])
def list_applications():
    return list_credit_applications()


@app.get("/credit-applications/{application_id}", response_model=CreditApplication)
def get_application(application_id: str):
    application = get_credit_application(application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Credit application not found")
    return application


@app.put(
    "/credit-applications/{application_id}/status",
    response_model=CreditApplication,
)
def update_application_status(
    application_id: str, data: CreditApplicationStatusUpdate
):
    application = update_credit_application_status(application_id, data.status)
    if application is None:
        raise HTTPException(status_code=404, detail="Credit application not found")
    return application
