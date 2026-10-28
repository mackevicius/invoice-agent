from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

DemoRole = Literal["Submitter", "Reviewer", "Admin"]


@dataclass(frozen=True)
class DemoPerson:
    company_id: UUID
    id: str
    role: DemoRole


class DemoCompany(BaseModel):
    id: UUID
    expires_at: datetime
