from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class InvoiceFile:
    filename: str
    content_type: str
    content: bytes


class InvoiceLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=1000)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class InvoiceFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_name: str = Field(min_length=1, max_length=200)
    invoice_number: str = Field(min_length=1, max_length=200)
    issued_on: date
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    lines: list[InvoiceLine] = Field(min_length=1)
    subtotal: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    tax: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    total: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class InvoiceReader(Protocol):
    def read(self, document: InvoiceFile) -> InvoiceFields | None: ...


@dataclass(frozen=True)
class ScriptedInvoiceReader:
    result: InvoiceFields | None | Exception

    def read(self, document: InvoiceFile) -> InvoiceFields | None:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result
