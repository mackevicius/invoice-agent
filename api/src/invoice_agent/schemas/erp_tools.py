from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Supplier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
