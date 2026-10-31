from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

DemoRole = Literal["Submitter", "Reviewer", "Admin"]


@dataclass(frozen=True)
class DemoPerson:
    company_id: UUID
    id: str
    role: DemoRole


class DemoCompany(BaseModel):
    id: UUID
    expires_at: datetime


class AutoApprovalLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    currency: Literal["EUR"] = "EUR"
