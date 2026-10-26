from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from psycopg.rows import dict_row

from invoice_agent.demo_company.api import DemoCompanies
from invoice_agent.invoice_reading.processing import InvoiceNotFound, InvoiceProcessing
from invoice_agent.invoice_reading.queue import InvoiceQueue, ProcessInvoiceJob
from invoice_agent.invoice_reading.reading import InvoiceFile
from invoice_agent.invoices.models import InvoiceDetail, InvoiceHeader

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}


def create_invoice_router(
    database_url: str,
    companies: DemoCompanies,
    processing: InvoiceProcessing,
    queue: InvoiceQueue,
) -> APIRouter:
    router = APIRouter(prefix="/api/invoices", tags=["Invoices"])

    @router.post("", status_code=202)
    async def upload_invoice(
        file: UploadFile,
        company_id: Annotated[UUID, Depends(companies.identify)],
    ) -> InvoiceDetail:
        try:
            content_type = (file.content_type or "").lower()
            if content_type not in SUPPORTED_CONTENT_TYPES:
                raise HTTPException(
                    status_code=415,
                    detail="Choose a PDF, PNG, JPEG, WebP, or GIF file.",
                )
            content = await file.read(MAX_UPLOAD_BYTES + 1)
            if not content:
                raise HTTPException(status_code=422, detail="Choose a non-empty file.")
            if len(content) > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413, detail="Invoice files must be 10 MB or smaller."
                )
            try:
                invoice = processing.upload(
                    company_id,
                    InvoiceFile(
                        filename=(file.filename or "invoice")[:200],
                        content_type=content_type,
                        content=content,
                    ),
                )
            except InvoiceNotFound as error:
                raise HTTPException(
                    status_code=401, detail="Start a Demo Company first."
                ) from error
            queue.enqueue(ProcessInvoiceJob(company_id, invoice.id))
            return invoice
        finally:
            await file.close()

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
    ) -> InvoiceDetail:
        invoice = processing.get(company_id, invoice_id)
        if invoice is None:
            raise HTTPException(status_code=404, detail="Invoice not found.")
        return invoice

    return router
