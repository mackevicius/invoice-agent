from dataclasses import dataclass
from typing import Protocol

from invoice_agent.schemas.invoice_fields import InvoiceFields
from invoice_agent.schemas.invoices import InvoiceFile


class InvoiceReader(Protocol):
    @property
    def uses_live_model(self) -> bool: ...

    def read(self, document: InvoiceFile) -> InvoiceFields | None: ...


@dataclass(frozen=True)
class ScriptedInvoiceReader:
    result: InvoiceFields | None | Exception

    @property
    def uses_live_model(self) -> bool:
        return False

    def read(self, document: InvoiceFile) -> InvoiceFields | None:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result
