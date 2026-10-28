from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from invoice_agent.routes.demo_company import require_demo_person
from invoice_agent.schemas.demo_company import DemoPerson
from invoice_agent.schemas.invoices import (
    InvoiceCounts,
    InvoiceDetail,
    InvoiceFile,
    InvoiceHeader,
    InvoiceRejection,
    InvoiceView,
)
from invoice_agent.services.demo_company import DemoCompanies
from invoice_agent.services.invoices import (
    InvoiceDecisionConflict,
    InvoiceNotFound,
    InvoicePermissionDenied,
    InvoiceProcessing,
)
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
    current_person = require_demo_person(companies)

    @router.post("", status_code=202)
    async def upload_invoice(
        file: UploadFile,
        person: Annotated[DemoPerson, Depends(current_person)],
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
                    person.company_id,
                    InvoiceFile(
                        filename=(file.filename or "invoice")[:200],
                        content_type=content_type,
                        content=content,
                    ),
                    submitted_by=person.id,
                )
            except InvoiceNotFound as error:
                raise HTTPException(
                    status_code=401, detail="Start a Demo Company first."
                ) from error
            queue.enqueue(ProcessInvoiceJob(person.company_id, invoice.id))
            return invoice
        finally:
            await file.close()

    @router.get("")
    def list_invoices(
        person: Annotated[DemoPerson, Depends(current_person)],
        view: InvoiceView = "all",
    ) -> list[InvoiceHeader]:
        return processing.list_headers(
            person.company_id, view=view, submitted_by=person.id
        )

    @router.get("/counts")
    def invoice_counts(
        person: Annotated[DemoPerson, Depends(current_person)],
    ) -> InvoiceCounts:
        return processing.counts(person)

    @router.get("/{invoice_id}")
    def get_invoice(
        invoice_id: UUID,
        person: Annotated[DemoPerson, Depends(current_person)],
    ) -> InvoiceDetail:
        invoice = processing.get(person.company_id, invoice_id, person=person)
        if invoice is None:
            raise HTTPException(status_code=404, detail="Invoice not found.")
        return invoice

    def record_decision(
        person: DemoPerson,
        invoice_id: UUID,
        decision: Literal["Approved", "Rejected"],
        rejection_reason: str | None = None,
    ) -> InvoiceDetail:
        try:
            return processing.decide(person, invoice_id, decision, rejection_reason)
        except InvoicePermissionDenied as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except InvoiceNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except InvoiceDecisionConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/{invoice_id}/approve")
    def approve_invoice(
        invoice_id: UUID,
        person: Annotated[DemoPerson, Depends(current_person)],
    ) -> InvoiceDetail:
        return record_decision(person, invoice_id, "Approved")

    @router.post("/{invoice_id}/reject")
    def reject_invoice(
        invoice_id: UUID,
        rejection: InvoiceRejection,
        person: Annotated[DemoPerson, Depends(current_person)],
    ) -> InvoiceDetail:
        return record_decision(
            person, invoice_id, "Rejected", rejection.rejection_reason
        )

    return router
