from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DemoCompany(BaseModel):
    id: UUID
    expires_at: datetime
