from dataclasses import dataclass
from typing import Protocol

from invoice_agent.schemas.invoice_fields import InvoiceFields


@dataclass(frozen=True)
class InvoiceFile:
    filename: str
    content_type: str
    content: bytes


class InvoiceReader(Protocol):
    def read(self, document: InvoiceFile) -> InvoiceFields | None: ...


@dataclass(frozen=True)
class ScriptedInvoiceReader:
    result: InvoiceFields | None | Exception

    def read(self, document: InvoiceFile) -> InvoiceFields | None:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result
