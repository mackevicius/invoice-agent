from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from invoice_agent.schemas.demo_company import DemoPerson
from invoice_agent.schemas.invoices import (
    InvoiceCounts,
    InvoiceDetail,
    InvoiceFile,
    InvoiceHeader,
    InvoiceView,
)

_VIEW_FILTERS: dict[InvoiceView, str] = {
    "all": "TRUE",
    "mine": "submitted_by = %(submitted_by)s",
    "review-queue": "status = 'In Review'",
    "done": "status IN ('Auto-Approved', 'Approved', 'Rejected')",
}


def skip_pending_steps(
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


class InvoiceNotFound(LookupError):
    pass


class InvoicePermissionDenied(PermissionError):
    pass


class InvoiceDecisionConflict(ValueError):
    pass


class Invoices:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def list_headers(
        self,
        company_id: UUID,
        *,
        view: InvoiceView = "all",
        submitted_by: str = "submitter",
    ) -> list[InvoiceHeader]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            invoices = connection.execute(
                sql.SQL("""SELECT id, invoice_number, supplier_name AS supplier,
                          total, currency, status, issued_on
                   FROM invoices WHERE company_id = %(company_id)s
                     AND {view_filter}
                   ORDER BY created_at DESC, id""").format(
                    view_filter=sql.SQL(_VIEW_FILTERS[view])
                ),
                {"company_id": company_id, "submitted_by": submitted_by},
            ).fetchall()
        return [InvoiceHeader.model_validate(invoice) for invoice in invoices]

    def counts(self, person: DemoPerson) -> InvoiceCounts:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            counts = connection.execute(
                """SELECT count(*) AS "all",
                          count(*) FILTER (WHERE submitted_by = %s) AS mine,
                          count(*) FILTER (WHERE status = 'In Review') AS review_queue,
                          count(*) FILTER (
                              WHERE status IN ('Auto-Approved', 'Approved', 'Rejected')
                          ) AS done
                   FROM invoices WHERE company_id = %s""",
                (person.id, person.company_id),
            ).fetchone()
        return InvoiceCounts.model_validate(counts)

    def get(
        self,
        company_id: UUID,
        invoice_id: UUID,
        *,
        person: DemoPerson | None = None,
    ) -> InvoiceDetail | None:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            invoice = connection.execute(
                """SELECT invoice.id, invoice_number, supplier_name AS supplier,
                          total, invoice.currency, status, issued_on,
                          file_name AS filename, read_fields AS fields, reasons,
                          comparison, submitted_by, rejection_reason,
                             invoice.auto_approval_limit,
                                  invoice.trace_url,
                          invoice.created_at AS received_at
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
        detail = InvoiceDetail.model_validate({**invoice, "steps": steps})
        if person is not None:
            try:
                self._check_decision_permission(person, detail)
            except (InvoicePermissionDenied, InvoiceDecisionConflict) as error:
                detail.decision_block_reason = str(error)
            else:
                detail.can_decide = True
        return detail

    def get_file(self, company_id: UUID, invoice_id: UUID) -> InvoiceFile | None:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            stored = connection.execute(
                """SELECT file_name, content_type, file_content
                   FROM invoices AS invoice
                   JOIN demo_companies AS company ON company.id = invoice.company_id
                   WHERE invoice.company_id = %s AND invoice.id = %s
                     AND company.expires_at > %s AND file_content IS NOT NULL""",
                (company_id, invoice_id, datetime.now(UTC)),
            ).fetchone()
        if stored is None:
            return None
        return InvoiceFile(
            filename=stored["file_name"],
            content_type=stored["content_type"],
            content=bytes(stored["file_content"]),
        )

    def _require(self, company_id: UUID, invoice_id: UUID) -> InvoiceDetail:
        invoice = self.get(company_id, invoice_id)
        if invoice is None:
            raise InvoiceNotFound("Invoice not found.")
        return invoice

    def _check_decision_permission(
        self, person: DemoPerson, invoice: InvoiceDetail
    ) -> None:
        if person.role != "Reviewer":
            raise InvoicePermissionDenied("Only a Reviewer can decide an Invoice.")
        if invoice.submitted_by == person.id:
            raise InvoicePermissionDenied("You cannot decide an Invoice you uploaded.")
        if invoice.status != "In Review":
            raise InvoiceDecisionConflict("Only an In Review Invoice can be decided.")
        if any(step.status in {"Pending", "Running"} for step in invoice.steps):
            raise InvoiceDecisionConflict("Invoice processing is still running.")

    def decide(
        self,
        person: DemoPerson,
        invoice_id: UUID,
        decision: Literal["Approved", "Rejected"],
        rejection_reason: str | None = None,
    ) -> InvoiceDetail:
        invoice = self._require(person.company_id, invoice_id)
        self._check_decision_permission(person, invoice)
        with psycopg.connect(self.database_url) as connection:
            company = connection.execute(
                """SELECT auto_approval_limit FROM demo_companies
                   WHERE id = %s AND expires_at > %s FOR SHARE""",
                (person.company_id, datetime.now(UTC)),
            ).fetchone()
            if company is None:
                raise InvoiceNotFound("Demo Company not found.")
            updated = connection.execute(
                """UPDATE invoices SET status = %s, rejection_reason = %s,
                          auto_approval_limit = %s
                   WHERE company_id = %s AND id = %s AND status = 'In Review'
                     AND submitted_by <> %s
                     AND NOT EXISTS (
                         SELECT 1 FROM invoice_steps
                         WHERE company_id = %s AND invoice_id = %s
                           AND status IN ('Pending', 'Running')
                     )
                     AND EXISTS (SELECT 1 FROM demo_companies
                                 WHERE id = %s AND expires_at > %s)
                   RETURNING id""",
                (
                    decision,
                    rejection_reason,
                    company[0],
                    person.company_id,
                    invoice_id,
                    person.id,
                    person.company_id,
                    invoice_id,
                    person.company_id,
                    datetime.now(UTC),
                ),
            ).fetchone()
        invoice = self._require(person.company_id, invoice_id)
        if updated is None:
            raise InvoiceDecisionConflict("Only an In Review Invoice can be decided.")
        return invoice
