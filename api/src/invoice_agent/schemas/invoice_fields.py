from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class InvoiceLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=1000)
    item_code: str | None = Field(default=None, min_length=1, max_length=200)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class InvoiceFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_name: str = Field(min_length=1, max_length=200)
    invoice_number: str = Field(min_length=1, max_length=200)
    purchase_order_number: str | None = Field(
        default=None, min_length=1, max_length=200
    )
    issued_on: date
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    lines: list[InvoiceLine] = Field(min_length=1)
    subtotal: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    tax: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    total: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class InvoiceReadResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice: InvoiceFields | None
