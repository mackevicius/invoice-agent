from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from invoice_agent.schemas.erp_tools import GoodsReceiptLine, PurchaseOrderLine
from invoice_agent.schemas.invoice_fields import InvoiceLine

ComparisonCell = Literal[
    "invoice.description",
    "invoice.quantity",
    "invoice.unit_price",
    "purchase_order.description",
    "purchase_order.quantity",
    "purchase_order.unit_price",
    "goods_receipt.quantity",
]


class PairedLine(BaseModel):
    line_number: int
    invoice: InvoiceLine
    purchase_order: PurchaseOrderLine | None
    paired_by: Literal["item_code", "description"] | None


class LineComparison(PairedLine):
    goods_receipt: GoodsReceiptLine | None
    unit_price_difference: Decimal | None
    unit_price_difference_percent: Decimal | None
    price_passed: bool
    quantity_passed: bool
    mismatched_cells: list[ComparisonCell] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
