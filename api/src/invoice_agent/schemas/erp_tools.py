from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Supplier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str


class PurchaseOrderLine(BaseModel):
    id: UUID
    description: str
    item_code: str | None = None
    quantity: Decimal
    unit_price: Decimal


class PurchaseOrder(BaseModel):
    id: UUID
    supplier_id: UUID
    number: str
    lines: list[PurchaseOrderLine]


class GoodsReceiptLine(BaseModel):
    purchase_order_line_id: UUID
    quantity: Decimal


class GoodsReceipt(BaseModel):
    purchase_order_id: UUID
    numbers: list[str]
    lines: list[GoodsReceiptLine]
