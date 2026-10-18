from uuid import uuid4
import os
import httpx
from fastapi import HTTPException
from .telemetry import tracer, logger

REMOTE = os.getenv("SERVICE_B_URL", "").rstrip("/")
_client = httpx.Client(timeout=httpx.Timeout(10, connect=2))

def remote(method, path, payload=None):
    with tracer.start_as_current_span({"POST": "credit.create", "PUT": "credit.status_update", "GET": "credit.read"}[method]):
        try:
            response = _client.request(method, REMOTE + path, json=payload)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            logger.info("credit.remote.success")
            return response.json()
        except httpx.HTTPError:
            logger.error("credit.remote.unavailable")
            raise HTTPException(status_code=503, detail="Credit storage unavailable")


from .models import (
    ApplicationStatus,
    CreditApplication,
    CreditApplicationCreate,
)


credit_applications: dict[str, CreditApplication] = {}


def create_credit_application(data: CreditApplicationCreate) -> CreditApplication:
    if REMOTE:
        return CreditApplication.model_validate(remote("POST", "/credit-applications", data.model_dump(mode="json")))
    application = CreditApplication(
        application_id=str(uuid4()),
        status=ApplicationStatus.PENDING,
        **data.model_dump(),
    )
    credit_applications[application.application_id] = application
    return application


def list_credit_applications() -> list[CreditApplication]:
    if REMOTE:
        return [CreditApplication.model_validate(row) for row in remote("GET", "/credit-applications")]
    return list(credit_applications.values())


def get_credit_application(application_id: str) -> CreditApplication | None:
    if REMOTE:
        row = remote("GET", "/credit-applications/" + application_id)
        return CreditApplication.model_validate(row) if row else None
    return credit_applications.get(application_id)


def update_credit_application_status(
    application_id: str, status: ApplicationStatus
) -> CreditApplication | None:
    if REMOTE:
        row = remote("PUT", "/credit-applications/" + application_id + "/status", {"status": status.value})
        return CreditApplication.model_validate(row) if row else None
    application = get_credit_application(application_id)
    if application is None:
        return None
    application.status = status
    return application
