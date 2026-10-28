import logging
from datetime import UTC, datetime
from typing import TypedDict
from uuid import UUID, uuid4

import psycopg
from langgraph.graph import END, START, StateGraph
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import JsonValue

from invoice_agent.clients.invoice_reader import InvoiceReader
from invoice_agent.schemas.invoices import InvoiceDetail, InvoiceFile, InvoiceHeader
from invoice_agent.services.erp_tools import ERPTools

logger = logging.getLogger(__name__)

INVOICE_STEPS = (
    "Read Invoice",
    "Find Supplier",
    "Find Purchase Order",
    "Find Goods Receipt",
    "Pair Lines",
    "Three-Way Match",
    "Check Duplicates",
    "Decide",
)


def _skip_pending_steps(
    connection: psycopg.Connection[tuple[object, ...]],
    company_id: UUID,
    invoice_id: UUID,
    reason: str,
) -> None:
    connection.execute(
        """UPDATE invoice_steps SET status = 'Skipped', outputs = %s,
                  completed_at = %s
           WHERE company_id = %s AND invoice_id = %s AND status = 'Pending'""",
        (Jsonb({"reason": reason}), datetime.now(UTC), company_id, invoice_id),
    )


class InvoiceRun(TypedDict):
    company_id: UUID
    invoice_id: UUID


class InvoiceNotFound(LookupError):
    pass


class InvoiceProcessing:
    def __init__(
        self, database_url: str, reader: InvoiceReader, erp_tools: ERPTools
    ) -> None:
        self.database_url = database_url
        self.reader = reader
        self.erp_tools = erp_tools
        graph = StateGraph(InvoiceRun)
        graph.add_node("read_invoice", self._read_invoice)
        graph.add_node("find_supplier", self._find_supplier)
        graph.add_edge(START, "read_invoice")
        graph.add_edge("read_invoice", "find_supplier")
        graph.add_edge("find_supplier", END)
        self.graph = graph.compile()

    def upload(self, company_id: UUID, document: InvoiceFile) -> InvoiceDetail:
        invoice_id = uuid4()
        now = datetime.now(UTC)
        with psycopg.connect(self.database_url) as connection:
            inserted = connection.execute(
                """INSERT INTO invoices
                   (id, company_id, status, created_at,
                    file_name, content_type, file_content)
                   SELECT %s, id, 'Processing', %s, %s, %s, %s
                   FROM demo_companies WHERE id = %s AND expires_at > %s
                   RETURNING id""",
                (
                    invoice_id,
                    now,
                    document.filename,
                    document.content_type,
                    document.content,
                    company_id,
                    now,
                ),
            ).fetchone()
            if inserted is None:
                raise InvoiceNotFound("Demo Company not found.")
            for position, name in enumerate(INVOICE_STEPS):
                connection.execute(
                    """INSERT INTO invoice_steps
                       (company_id, invoice_id, name, position, status, inputs)
                       VALUES (%s, %s, %s, %s, 'Pending', %s)""",
                    (
                        company_id,
                        invoice_id,
                        name,
                        position,
                        Jsonb(
                            {
                                "filename": document.filename,
                                "content_type": document.content_type,
                            }
                            if position == 0
                            else {}
                        ),
                    ),
                )
        return self._require(company_id, invoice_id)

    def process(self, company_id: UUID, invoice_id: UUID) -> InvoiceDetail:
        self.graph.invoke({"company_id": company_id, "invoice_id": invoice_id})
        return self._require(company_id, invoice_id)

    def list_headers(self, company_id: UUID) -> list[InvoiceHeader]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            invoices = connection.execute(
                """SELECT id, invoice_number, supplier_name AS supplier,
                          total, currency, status, issued_on
                   FROM invoices WHERE company_id = %s
                   ORDER BY created_at DESC, id""",
                (company_id,),
            ).fetchall()
        return [InvoiceHeader.model_validate(invoice) for invoice in invoices]

    def get(self, company_id: UUID, invoice_id: UUID) -> InvoiceDetail | None:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            invoice = connection.execute(
                """SELECT invoice.id, invoice_number, supplier_name AS supplier,
                          total, invoice.currency, status, issued_on,
                          file_name AS filename, read_fields AS fields, reasons
                   FROM invoices AS invoice
                   JOIN demo_companies AS company ON company.id = invoice.company_id
                   WHERE company_id = %s AND invoice.id = %s
                     AND company.expires_at > %s""",
                (company_id, invoice_id, datetime.now(UTC)),
            ).fetchone()
            if invoice is None:
                return None
            steps = connection.execute(
                """SELECT name, status, inputs, outputs, started_at, completed_at
                   FROM invoice_steps WHERE company_id = %s AND invoice_id = %s
                   ORDER BY position""",
                (company_id, invoice_id),
            ).fetchall()
        return InvoiceDetail.model_validate({**invoice, "steps": steps})

    def _require(self, company_id: UUID, invoice_id: UUID) -> InvoiceDetail:
        invoice = self.get(company_id, invoice_id)
        if invoice is None:
            raise InvoiceNotFound("Invoice not found.")
        return invoice

    def _read_invoice(self, state: InvoiceRun) -> InvoiceRun:
        company_id, invoice_id = state["company_id"], state["invoice_id"]
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            claimed = connection.execute(
                """UPDATE invoice_steps SET status = 'Running', started_at = %s
                   WHERE company_id = %s AND invoice_id = %s AND status = 'Pending'
                     AND name = 'Read Invoice'
                     AND EXISTS (SELECT 1 FROM demo_companies
                                 WHERE id = %s AND expires_at > %s)
                   RETURNING invoice_id""",
                (
                    datetime.now(UTC),
                    company_id,
                    invoice_id,
                    company_id,
                    datetime.now(UTC),
                ),
            ).fetchone()
            if claimed is None:
                return state
            stored = connection.execute(
                """SELECT file_name, content_type, file_content FROM invoices
                   WHERE company_id = %s AND id = %s""",
                (company_id, invoice_id),
            ).fetchone()
        if stored is None:
            raise InvoiceNotFound("Invoice not found.")
        try:
            fields = self.reader.read(
                InvoiceFile(
                    filename=stored["file_name"],
                    content_type=stored["content_type"],
                    content=bytes(stored["file_content"]),
                )
            )
        except Exception:
            logger.exception("Invoice reading failed for %s", invoice_id)
            self._fail_read(
                company_id,
                invoice_id,
                "Invoice reading is unavailable. "
                "A Reviewer needs to check this Invoice.",
            )
            return state
        if fields is None:
            self._fail_read(
                company_id, invoice_id, "This file could not be read as an Invoice."
            )
            return state
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """UPDATE invoices SET supplier_name = %s, invoice_number = %s,
                          total = %s, currency = %s, issued_on = %s,
                          read_fields = %s
                   WHERE company_id = %s AND id = %s""",
                (
                    fields.supplier_name,
                    fields.invoice_number,
                    fields.total,
                    fields.currency,
                    fields.issued_on,
                    Jsonb(fields.model_dump(mode="json")),
                    company_id,
                    invoice_id,
                ),
            )
            for line in fields.lines:
                connection.execute(
                    """INSERT INTO invoice_lines
                       (id, company_id, invoice_id, description, quantity, unit_price)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (
                        uuid4(),
                        company_id,
                        invoice_id,
                        line.description,
                        line.quantity,
                        line.unit_price,
                    ),
                )
            connection.execute(
                """UPDATE invoice_steps SET status = 'Completed', outputs = %s,
                          completed_at = %s
                                     WHERE company_id = %s AND invoice_id = %s
                                         AND name = 'Read Invoice'""",
                (
                    Jsonb(fields.model_dump(mode="json")),
                    datetime.now(UTC),
                    company_id,
                    invoice_id,
                ),
            )
        return state

    def _find_supplier(self, state: InvoiceRun) -> InvoiceRun:
        company_id, invoice_id = state["company_id"], state["invoice_id"]
        invoice = self._require(company_id, invoice_id)
        if invoice.fields is None:
            return state
        name = invoice.fields.supplier_name
        with psycopg.connect(self.database_url) as connection:
            claimed = connection.execute(
                """UPDATE invoice_steps SET status = 'Running', inputs = %s,
                          started_at = %s
                   WHERE company_id = %s AND invoice_id = %s
                     AND name = 'Find Supplier' AND status = 'Pending'
                   RETURNING invoice_id""",
                (
                    Jsonb({"name": name}),
                    datetime.now(UTC),
                    company_id,
                    invoice_id,
                ),
            ).fetchone()
        if claimed is None:
            return state
        outputs: dict[str, JsonValue]
        try:
            supplier = self.erp_tools.find_supplier(company_id, name)
        except Exception:
            logger.exception("Supplier lookup failed for %s", invoice_id)
            supplier = None
            reason = (
                "Supplier lookup is unavailable. "
                "A Reviewer needs to check this Invoice."
            )
            step_status = "Failed"
            outputs = {"reason": reason}
        else:
            reason = (
                "Purchase Order and Goods Receipt checks are still required."
                if supplier is not None
                else "Unknown Supplier"
            )
            step_status = "Completed"
            outputs = {
                "supplier": supplier.model_dump(mode="json")
                if supplier is not None
                else None
            }
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """UPDATE invoices SET supplier_id = %s,
                          status = 'In Review', reasons = %s
                   WHERE company_id = %s AND id = %s""",
                (
                    supplier.id if supplier is not None else None,
                    Jsonb([reason]),
                    company_id,
                    invoice_id,
                ),
            )
            connection.execute(
                """UPDATE invoice_steps SET status = %s, outputs = %s,
                          completed_at = %s
                   WHERE company_id = %s AND invoice_id = %s
                     AND name = 'Find Supplier'""",
                (
                    step_status,
                    Jsonb(outputs),
                    datetime.now(UTC),
                    company_id,
                    invoice_id,
                ),
            )
            _skip_pending_steps(connection, company_id, invoice_id, reason)
        return state

    def _fail_read(self, company_id: UUID, invoice_id: UUID, reason: str) -> None:
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """UPDATE invoices SET status = 'In Review', reasons = %s
                   WHERE company_id = %s AND id = %s""",
                (Jsonb([reason]), company_id, invoice_id),
            )
            connection.execute(
                """UPDATE invoice_steps SET status = 'Failed', outputs = %s,
                          completed_at = %s
                                     WHERE company_id = %s AND invoice_id = %s
                                         AND name = 'Read Invoice'""",
                (
                    Jsonb({"reason": reason}),
                    datetime.now(UTC),
                    company_id,
                    invoice_id,
                ),
            )
            _skip_pending_steps(connection, company_id, invoice_id, reason)
