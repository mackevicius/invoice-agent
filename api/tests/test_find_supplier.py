from contextlib import closing
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from invoice_agent.clients.invoice_reader import ScriptedInvoiceReader
from invoice_agent.schemas.erp_tools import Supplier
from invoice_agent.schemas.invoice_fields import InvoiceFields, InvoiceLine
from invoice_agent.schemas.invoices import InvoiceFile
from invoice_agent.services.erp_tools import ERPTools
from invoice_agent.services.invoices import InvoiceProcessing


class UnavailableERPTools(ERPTools):
    def find_supplier(self, company_id: UUID, name: str) -> Supplier | None:
        raise RuntimeError("ERP unavailable")


@pytest.fixture
def supplier_invoice_fields() -> InvoiceFields:
    return InvoiceFields(
        supplier_name="Paper & Co.",
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


@pytest.mark.parametrize(
    "supplier_name", ["Paper & Co.", "paper & co.", "PAPER CO", "P.a.p.e.r & C.o."]
)
def test_known_supplier_is_recorded(
    client: TestClient,
    database_url: str,
    erp_tools: ERPTools,
    supplier_invoice_fields: InvoiceFields,
    supplier_name: str,
) -> None:
    company_id = UUID(client.post("/api/demo-company").json()["id"])
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(
            supplier_invoice_fields.model_copy(update={"supplier_name": supplier_name})
        ),
        erp_tools=erp_tools,
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

    supplier_step = next(step for step in result.steps if step.name == "Find Supplier")
    assert supplier_step.status == "Completed"
    assert supplier_step.inputs == {"name": supplier_name}
    assert supplier_step.outputs is not None
    supplier = supplier_step.outputs["supplier"]
    assert isinstance(supplier, dict)
    assert supplier["name"] == "Paper & Co."
    assert isinstance(supplier["id"], str)
    assert UUID(supplier["id"])
    assert supplier_step.started_at is not None
    assert supplier_step.completed_at is not None
    assert "Unknown Supplier" not in result.reasons
    assert processing.get(company_id, uploaded.id) == result


def test_unavailable_erp_goes_in_review(
    client: TestClient,
    database_url: str,
    supplier_invoice_fields: InvoiceFields,
) -> None:
    company_id = UUID(client.post("/api/demo-company").json()["id"])
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(supplier_invoice_fields),
        erp_tools=UnavailableERPTools(database_url),
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

    reason = "Supplier lookup is unavailable. A Reviewer needs to check this Invoice."
    assert result.status == "In Review"
    assert result.reasons == [reason]
    assert result.fields == supplier_invoice_fields
    assert result.steps[0].status == "Completed"
    assert result.steps[1].status == "Failed"
    assert result.steps[1].outputs == {"reason": reason}
    assert result.steps[1].completed_at is not None
    assert all(step.status == "Skipped" for step in result.steps[2:])
    assert processing.get(company_id, uploaded.id) == result


@pytest.mark.parametrize("supplier_name", ["Unknown Supplier Ltd.", "Paper", "---"])
def test_unknown_supplier_stops_the_run(
    client: TestClient,
    database_url: str,
    erp_tools: ERPTools,
    supplier_invoice_fields: InvoiceFields,
    supplier_name: str,
) -> None:
    company_id = UUID(client.post("/api/demo-company").json()["id"])
    fields = supplier_invoice_fields.model_copy(update={"supplier_name": supplier_name})
    processing = InvoiceProcessing(
        database_url, reader=ScriptedInvoiceReader(fields), erp_tools=erp_tools
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
    assert result.reasons == ["Unknown Supplier"]
    assert result.fields == fields
    assert result.steps[0].status == "Completed"
    assert result.steps[1].name == "Find Supplier"
    assert result.steps[1].status == "Completed"
    assert result.steps[1].outputs == {"supplier": None}
    assert [step.name for step in result.steps[2:]] == [
        "Find Purchase Order",
        "Find Goods Receipt",
        "Pair Lines",
        "Three-Way Match",
        "Check Duplicates",
        "Decide",
    ]
    for step in result.steps[2:]:
        assert step.status == "Skipped"
        assert step.outputs == {"reason": "Unknown Supplier"}
        assert step.started_at is None
        assert step.completed_at is not None
    assert processing.get(company_id, uploaded.id) == result


def test_supplier_lookup_is_scoped_to_demo_company(
    client: TestClient,
    database_url: str,
    erp_tools: ERPTools,
    supplier_invoice_fields: InvoiceFields,
) -> None:
    company_id = UUID(client.post("/api/demo-company").json()["id"])
    with closing(TestClient(client.app)) as other_visitor:
        other_company_id = UUID(other_visitor.post("/api/demo-company").json()["id"])
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(supplier_invoice_fields),
        erp_tools=erp_tools,
    )
    document = InvoiceFile(
        filename="invoice.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4\nInvoice",
    )
    first = processing.process(company_id, processing.upload(company_id, document).id)
    second = processing.process(
        other_company_id, processing.upload(other_company_id, document).id
    )

    assert first.steps[1].outputs is not None
    assert second.steps[1].outputs is not None
    first_supplier = first.steps[1].outputs["supplier"]
    second_supplier = second.steps[1].outputs["supplier"]
    assert isinstance(first_supplier, dict)
    assert isinstance(second_supplier, dict)
    assert first_supplier["name"] == second_supplier["name"] == "Paper & Co."
    assert first_supplier["id"] != second_supplier["id"]
