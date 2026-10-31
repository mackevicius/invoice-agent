from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from invoice_agent.clients.invoice_reader import ScriptedInvoiceReader
from invoice_agent.schemas.invoice_fields import InvoiceFields
from invoice_agent.schemas.invoices import InvoiceDetail, InvoiceFile
from invoice_agent.services.daily_ai_limit import DailyAILimit
from invoice_agent.services.erp_tools import ERPTools
from invoice_agent.services.invoices import InvoiceProcessing


@pytest.mark.parametrize("total", ["3214.08", "4999.99"])
def test_known_supplier_with_passing_checks_under_the_limit_is_auto_approved(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    total: str,
) -> None:
    fields = matching_fields.model_copy(update={"total": Decimal(total)})

    result = process_invoice(fields)

    assert result.status == "Auto-Approved"
    assert result.reasons == []
    assert result.auto_approval_limit == Decimal("5000.00")
    assert all(step.status == "Completed" for step in result.steps)
    decision = result.steps[-1]
    assert decision.name == "Decide"
    assert decision.outputs is not None
    assert decision.outputs["status"] == "Auto-Approved"
    assert decision.outputs["reasons"] == []


@pytest.mark.parametrize("total", ["5000.00", "5000.01"])
def test_total_at_or_above_the_auto_approval_limit_needs_review(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    total: str,
) -> None:
    fields = matching_fields.model_copy(update={"total": Decimal(total)})

    result = process_invoice(fields)

    assert result.status == "In Review"
    assert result.reasons == [
        "Invoice total is at or above the Auto-Approval Limit of EUR 5,000.00."
    ]
    assert result.auto_approval_limit == Decimal("5000.00")
    decision = result.steps[-1]
    assert decision.status == "Completed"
    assert decision.inputs["auto_approval_limit"] == "5000.00"
    assert decision.outputs is not None
    assert decision.outputs["reasons"] == result.reasons


def test_an_invoice_in_another_currency_needs_review_even_when_lines_match(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
) -> None:
    fields = matching_fields.model_copy(update={"currency": "USD"})

    result = process_invoice(fields)

    assert result.status == "In Review"
    assert result.reasons == [
        "Invoice currency USD does not match the Demo Company currency EUR."
    ]
    assert result.auto_approval_limit == Decimal("5000.00")


def test_an_unknown_supplier_is_never_auto_approved(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
) -> None:
    fields = matching_fields.model_copy(update={"supplier_name": "Unknown business"})

    result = process_invoice(fields)

    assert result.status == "In Review"
    assert result.reasons == ["Unknown Supplier"]
    assert all(step.status == "Skipped" for step in result.steps[2:])


def test_a_possible_duplicate_is_never_auto_approved(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
) -> None:
    process_invoice(matching_fields)

    result = process_invoice(
        matching_fields.model_copy(update={"invoice_number": "INV-RENUMBERED"})
    )

    assert result.status == "In Review"
    assert result.reasons == [
        "Possible Duplicate: INV-MATCH-42 has the same total "
        "and was received within 30 days."
    ]


def test_a_model_pairing_choice_cannot_override_any_review_reason(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    pairing_choices: dict[str, str | UUID | Exception | None],
) -> None:
    process_invoice(matching_fields)
    description = "A4 recycled paper in boxes"
    pairing_choices[description] = "Recycled A4 paper, box"
    line = matching_fields.lines[0].model_copy(
        update={
            "description": description,
            "unit_price": Decimal("120.00"),
            "quantity": Decimal("30"),
        }
    )

    result = process_invoice(
        matching_fields.model_copy(
            update={"lines": [line], "total": Decimal("5000.01")}
        )
    )

    assert result.status == "In Review"
    assert result.comparison[0].paired_by == "meaning"
    assert result.reasons == [
        f"Line 1 ({description}): unit price is more than 2% above the Purchase Order.",
        f"Line 1 ({description}): invoiced quantity does not equal received quantity.",
        "Duplicate Invoice: INV-MATCH-42 was already received.",
        "Invoice total is at or above the Auto-Approval Limit of EUR 5,000.00.",
    ]
    assert result.steps[-1].inputs["three_way_match_passed"] is False
    assert result.steps[-1].inputs["duplicate_check_passed"] is False


def test_the_limit_is_read_when_an_invoice_is_decided_not_when_it_is_uploaded(
    client: TestClient,
    matching_company: UUID,
    matching_fields: InvoiceFields,
    database_url: str,
    erp_tools: ERPTools,
) -> None:
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(matching_fields),
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
    )
    uploaded = processing.upload(
        matching_company,
        InvoiceFile(
            filename="invoice.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4\nInvoice",
        ),
    )
    assert uploaded.auto_approval_limit is None
    changed = client.put(
        "/api/demo-company/auto-approval-limit",
        headers={"X-Demo-Role": "Admin"},
        json={"amount": "3000.00"},
    )
    assert changed.status_code == 200

    result = processing.process(matching_company, uploaded.id)

    assert result.status == "In Review"
    assert result.reasons == [
        "Invoice total is at or above the Auto-Approval Limit of EUR 3,000.00."
    ]
    assert result.auto_approval_limit == Decimal("3000.00")
    assert processing.get(matching_company, uploaded.id) == result
