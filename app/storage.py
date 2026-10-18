"""Service B: credit operations delegated to data-service."""
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator

from .models import CreditApplication, CreditApplicationCreate, CreditApplicationStatusUpdate
from .telemetry import configure, tracer, logger, flush

DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:8002").rstrip("/")
_client = httpx.Client(timeout=httpx.Timeout(8, connect=2))


@asynccontextmanager
async def lifespan(app):
    yield
    _client.close()
    flush()


app = FastAPI(title="Credit storage service", lifespan=lifespan)
configure(app)
Instrumentator().instrument(app).expose(app)


def remote(method, path, payload=None):
    with tracer.start_as_current_span("credit.data.request"):
        try:
            response = _client.request(method, DATA_SERVICE_URL + path, json=payload)
            if response.status_code == 404:
                raise HTTPException(404, "Credit application not found")
            response.raise_for_status()
        except httpx.HTTPError:
            logger.error("credit.data.unavailable")
            raise HTTPException(503, "Credit storage unavailable") from None
        logger.info("credit.data.success")
        return response.json()


@app.get("/health")
def health():
    return remote("GET", "/health")


@app.post("/credit-applications", response_model=CreditApplication, status_code=201)
def create(data: CreditApplicationCreate):
    return remote("POST", "/credit-applications", data.model_dump(mode="json"))


@app.get("/credit-applications", response_model=list[CreditApplication])
def listing():
    return remote("GET", "/credit-applications")


@app.get("/credit-applications/{application_id}", response_model=CreditApplication)
def get(application_id: str):
    return remote("GET", "/credit-applications/" + application_id)


@app.put("/credit-applications/{application_id}/status", response_model=CreditApplication)
def status(application_id: str, data: CreditApplicationStatusUpdate):
    return remote("PUT", "/credit-applications/" + application_id + "/status", data.model_dump(mode="json"))
