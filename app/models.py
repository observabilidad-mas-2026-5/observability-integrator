from enum import Enum

from pydantic import BaseModel, Field


class ApplicationStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class CreditApplicationCreate(BaseModel):
    customer_name: str = Field(min_length=1)
    document_number: str = Field(min_length=1)
    requested_amount: float = Field(gt=0)


class CreditApplication(CreditApplicationCreate):
    application_id: str
    status: ApplicationStatus


class CreditApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus
