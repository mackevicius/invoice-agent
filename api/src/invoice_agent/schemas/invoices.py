from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, JsonValue

from invoice_agent.schemas.invoice_fields import InvoiceFields


class InvoiceHeader(BaseModel):
    id: UUID
    invoice_number: str | None
    supplier: str | None
    total: Decimal | None
    currency: str
    status: Literal["Processing", "In Review", "Auto-Approved", "Approved", "Rejected"]
    issued_on: date | None


class InvoiceStep(BaseModel):
    name: str
    status: Literal["Pending", "Running", "Completed", "Failed"]
    inputs: dict[str, JsonValue]
    outputs: dict[str, JsonValue] | None
    started_at: datetime | None
    completed_at: datetime | None


class InvoiceDetail(InvoiceHeader):
    filename: str | None
    fields: InvoiceFields | None
    reasons: list[str] = Field(default_factory=list)
    steps: list[InvoiceStep] = Field(default_factory=list)
