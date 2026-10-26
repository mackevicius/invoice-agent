from base64 import b64decode
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient

from invoice_agent.clients.invoice_reader import InvoiceFile, ScriptedInvoiceReader
from invoice_agent.schemas.invoice_fields import InvoiceFields, InvoiceLine
from invoice_agent.services.invoice_processing import InvoiceProcessing


def test_read_fields_and_recorded_step(client: TestClient, database_url: str) -> None:
    company_id = UUID(client.post("/api/demo-company").json()["id"])
    fields = InvoiceFields(
        supplier_name="Baltic Office Supplies",
        invoice_number="INV-2026-42",
        issued_on=date(2026, 10, 20),
        currency="EUR",
        lines=[
            InvoiceLine(
                description="Printer paper",
                quantity=Decimal("3"),
                unit_price=Decimal("12.50"),
            )
        ],
        subtotal=Decimal("37.50"),
        tax=Decimal("7.88"),
        total=Decimal("45.38"),
    )
    processing = InvoiceProcessing(database_url, reader=ScriptedInvoiceReader(fields))
    document = InvoiceFile(
        filename="invoice.png",
        content_type="image/png",
        content=b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
            "/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
        ),
    )

    uploaded = processing.upload(company_id, document)

    assert uploaded.status == "Processing"
    assert uploaded.fields is None
    assert uploaded.steps[0].status == "Pending"

    result = processing.process(company_id, uploaded.id)

    assert result.fields == fields
    assert result.supplier == "Baltic Office Supplies"
    assert result.invoice_number == "INV-2026-42"
    assert result.total == Decimal("45.38")
    assert result.steps[0].name == "Read Invoice"
    assert result.steps[0].status == "Completed"
    assert result.steps[0].inputs == {
        "filename": "invoice.png",
        "content_type": "image/png",
    }
    assert result.steps[0].outputs == fields.model_dump(mode="json")
    assert processing.get(company_id, uploaded.id) == result


def test_unreadable_file_goes_in_review(client: TestClient, database_url: str) -> None:
    company_id = UUID(client.post("/api/demo-company").json()["id"])
    processing = InvoiceProcessing(database_url, reader=ScriptedInvoiceReader(None))
    uploaded = processing.upload(
        company_id,
        InvoiceFile(
            filename="unreadable.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4\nunreadable document",
        ),
    )

    result = processing.process(company_id, uploaded.id)

    assert result.status == "In Review"
    assert result.fields is None
    assert result.reasons == ["This file could not be read as an Invoice."]
    assert result.steps[0].status == "Failed"
    assert result.steps[0].outputs == {
        "reason": "This file could not be read as an Invoice."
    }
    assert result.steps[0].started_at is not None
    assert result.steps[0].completed_at is not None
    assert processing.get(company_id, uploaded.id) == result


def test_model_failure_goes_in_review(client: TestClient, database_url: str) -> None:
    company_id = UUID(client.post("/api/demo-company").json()["id"])
    processing = InvoiceProcessing(
        database_url, reader=ScriptedInvoiceReader(RuntimeError("Model unavailable"))
    )
    uploaded = processing.upload(
        company_id,
        InvoiceFile(
            filename="invoice.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4\nInvoice",
        ),
    )

    result = processing.process(company_id, uploaded.id)

    assert result.status == "In Review"
    assert result.fields is None
    assert result.reasons == [
        "Invoice reading is unavailable. A Reviewer needs to check this Invoice."
    ]
    assert result.steps[0].status == "Failed"
    assert processing.get(company_id, uploaded.id) == result
