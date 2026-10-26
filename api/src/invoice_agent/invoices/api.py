from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel

from invoice_agent.demo_company.api import DemoCompanies


class InvoiceHeader(BaseModel):
    id: UUID
    invoice_number: str
    supplier: str
    total: Decimal
    currency: str
    status: Literal["Processing", "In Review", "Auto-Approved", "Approved", "Rejected"]
    issued_on: date


def create_invoice_router(database_url: str, companies: DemoCompanies) -> APIRouter:
    router = APIRouter(prefix="/api/invoices", tags=["Invoices"])

    @router.get("")
    def list_invoices(
        company_id: Annotated[UUID, Depends(companies.identify)],
    ) -> list[InvoiceHeader]:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            invoices = connection.execute(
                """SELECT id, invoice_number, supplier_name AS supplier,
                          total, currency, status, issued_on
                   FROM invoices WHERE company_id = %s
                   ORDER BY created_at DESC, id""",
                (company_id,),
            ).fetchall()
        return [InvoiceHeader.model_validate(invoice) for invoice in invoices]

    @router.get("/{invoice_id}")
    def get_invoice(
        invoice_id: UUID,
        company_id: Annotated[UUID, Depends(companies.identify)],
    ) -> InvoiceHeader:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            invoice = connection.execute(
                """SELECT id, invoice_number, supplier_name AS supplier,
                          total, currency, status, issued_on
                   FROM invoices WHERE company_id = %s AND id = %s""",
                (company_id, invoice_id),
            ).fetchone()
        if invoice is None:
            raise HTTPException(status_code=404, detail="Invoice not found.")
        return InvoiceHeader.model_validate(invoice)

    return router
