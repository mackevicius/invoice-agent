from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from invoice_agent.routes.demo_company import require_demo_company
from invoice_agent.schemas.invoices import InvoiceDetail, InvoiceFile, InvoiceHeader
from invoice_agent.services.demo_company import DemoCompanies
from invoice_agent.services.invoices import InvoiceNotFound, InvoiceProcessing
from invoice_agent.workers.invoice_queue import InvoiceQueue, ProcessInvoiceJob

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}


def create_invoice_router(
    companies: DemoCompanies,
    processing: InvoiceProcessing,
    queue: InvoiceQueue,
) -> APIRouter:
    router = APIRouter(prefix="/api/invoices", tags=["Invoices"])
    current_company_id = require_demo_company(companies)

    @router.post("", status_code=202)
    async def upload_invoice(
        file: UploadFile,
        company_id: Annotated[UUID, Depends(current_company_id)],
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
        company_id: Annotated[UUID, Depends(current_company_id)],
    ) -> list[InvoiceHeader]:
        return processing.list_headers(company_id)

    @router.get("/{invoice_id}")
    def get_invoice(
        invoice_id: UUID,
        company_id: Annotated[UUID, Depends(current_company_id)],
    ) -> InvoiceDetail:
        invoice = processing.get(company_id, invoice_id)
        if invoice is None:
            raise HTTPException(status_code=404, detail="Invoice not found.")
        return invoice

    return router
