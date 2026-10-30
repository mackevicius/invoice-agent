from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LineChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purchase_order_line_id: UUID | None
