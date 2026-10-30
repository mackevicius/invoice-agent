from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, JsonValue, StringConstraints

from invoice_agent.schemas.invoice_fields import InvoiceFields
from invoice_agent.schemas.three_way_match import LineComparison

InvoiceView = Literal["all", "mine", "review-queue", "done"]


class InvoiceCounts(BaseModel):
    all: int
    mine: int
    review_queue: int
    done: int


@dataclass(frozen=True)
class InvoiceFile:
    filename: str
    content_type: str
    content: bytes


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
    status: Literal["Pending", "Running", "Completed", "Failed", "Skipped"]
    inputs: dict[str, JsonValue]
    outputs: dict[str, JsonValue] | None
    started_at: datetime | None
    completed_at: datetime | None


class InvoiceDetail(InvoiceHeader):
    filename: str | None
    fields: InvoiceFields | None
    received_at: datetime
    submitted_by: str = "submitter"
    rejection_reason: str | None = None
    can_decide: bool = False
    decision_block_reason: str | None = None
    comparison: list[LineComparison] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    steps: list[InvoiceStep] = Field(default_factory=list)


class InvoiceRejection(BaseModel):
    rejection_reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
