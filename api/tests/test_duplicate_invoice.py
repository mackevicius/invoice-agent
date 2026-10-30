from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import psycopg
import pytest
import time_machine
from fastapi.testclient import TestClient

from invoice_agent.clients.invoice_reader import ScriptedInvoiceReader
from invoice_agent.schemas.erp_tools import EarlierInvoice
from invoice_agent.schemas.invoice_fields import InvoiceFields
from invoice_agent.schemas.invoices import InvoiceDetail, InvoiceFile
from invoice_agent.services.daily_ai_limit import DailyAILimit
from invoice_agent.services.erp_tools import ERPTools
from invoice_agent.services.invoices import InvoiceProcessing


class UnavailableInvoiceHistory(ERPTools):
    def find_earlier_invoices(
        self, company_id: UUID, supplier_id: UUID, invoice_id: UUID
    ) -> list[EarlierInvoice]:
        raise RuntimeError("Invoice history unavailable")


def test_same_supplier_and_invoice_number_is_a_duplicate(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
) -> None:
    process_invoice(matching_fields)

    result = process_invoice(matching_fields)

    assert result.status == "In Review"
    assert result.reasons == ["Duplicate Invoice: INV-MATCH-42 was already received."]
    assert result.steps[6].name == "Check Duplicates"
    assert result.steps[6].status == "Completed"


@pytest.mark.parametrize(
    ("age", "expected_reasons"),
    [
        (
            timedelta(days=29),
            [
                "Possible Duplicate: INV-MATCH-42 has the same total "
                "and was received within 30 days."
            ],
        ),
        (
            timedelta(days=30),
            [
                "Possible Duplicate: INV-MATCH-42 has the same total "
                "and was received within 30 days."
            ],
        ),
        (timedelta(days=30, seconds=1), ["All checks passed"]),
    ],
    ids=["inside-30-days", "exactly-30-days", "outside-30-days"],
)
def test_possible_duplicate_uses_when_the_earlier_invoice_was_received(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    database_url: str,
    age: timedelta,
    expected_reasons: list[str],
) -> None:
    now = datetime.now(UTC)
    with time_machine.travel(now, tick=False):
        earlier = process_invoice(matching_fields)
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "UPDATE invoices SET created_at = %s WHERE id = %s",
                (now - age, earlier.id),
            )

        result = process_invoice(
            matching_fields.model_copy(update={"invoice_number": "INV-RENUMBERED"})
        )

    assert result.status == "In Review"
    assert result.reasons == expected_reasons
    assert result.steps[6].status == "Completed"


@pytest.mark.parametrize(
    ("purchase_order_number", "unit_price", "match_reason"),
    [
        (None, Decimal("111.60"), "No Purchase Order is named on this Invoice."),
        (
            "PO-NOT-FOUND",
            Decimal("111.60"),
            "Purchase Order PO-NOT-FOUND was not found for this Supplier.",
        ),
        (
            "PO-1002",
            Decimal("120.00"),
            "Line 1 (Recycled A4 paper, box): unit price is more than 2% "
            "above the Purchase Order.",
        ),
    ],
    ids=["no-purchase-order", "missing-purchase-order", "price-failure"],
)
def test_duplicate_check_keeps_every_matching_failure_reason(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    purchase_order_number: str | None,
    unit_price: Decimal,
    match_reason: str,
) -> None:
    process_invoice(matching_fields)

    result = process_invoice(
        matching_fields.model_copy(
            update={
                "purchase_order_number": purchase_order_number,
                "lines": [
                    matching_fields.lines[0].model_copy(
                        update={"unit_price": unit_price}
                    )
                ],
            }
        )
    )

    assert result.status == "In Review"
    assert result.reasons == [
        match_reason,
        "Duplicate Invoice: INV-MATCH-42 was already received.",
    ]
    assert result.steps[6].status == "Completed"
    assert result.steps[7].status == "Completed"


def test_unavailable_invoice_history_keeps_matching_failures_and_goes_in_review(
    database_url: str,
    matching_company: UUID,
    matching_fields: InvoiceFields,
) -> None:
    fields = matching_fields.model_copy(
        update={
            "lines": [
                matching_fields.lines[0].model_copy(
                    update={"unit_price": Decimal("120.00")}
                )
            ]
        }
    )
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(fields),
        erp_tools=UnavailableInvoiceHistory(database_url),
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

    result = processing.process(matching_company, uploaded.id)

    reason = (
        "Duplicate Invoice check is unavailable. "
        "A Reviewer needs to check this Invoice."
    )
    assert result.status == "In Review"
    assert result.reasons == [
        "Line 1 (Recycled A4 paper, box): unit price is more than 2% "
        "above the Purchase Order.",
        reason,
    ]
    assert result.steps[6].status == "Failed"
    assert result.steps[6].outputs == {"reason": reason}
    assert result.steps[7].status == "Completed"
    assert processing.get(matching_company, uploaded.id) == result


def test_invoice_is_not_its_own_duplicate(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
) -> None:
    result = process_invoice(matching_fields)

    assert result.reasons == ["All checks passed"]
    assert result.steps[6].outputs == {"duplicates": []}


def test_exact_duplicate_has_no_age_or_total_limit(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    database_url: str,
) -> None:
    earlier = process_invoice(matching_fields)
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "UPDATE invoices SET created_at = %s WHERE id = %s",
            (datetime.now(UTC) - timedelta(days=31), earlier.id),
        )

    result = process_invoice(
        matching_fields.model_copy(
            update={"tax": Decimal("536.68"), "total": Decimal("3215.08")}
        )
    )

    assert result.reasons == ["Duplicate Invoice: INV-MATCH-42 was already received."]


def test_different_number_and_total_is_not_a_possible_duplicate(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
) -> None:
    process_invoice(matching_fields)

    result = process_invoice(
        matching_fields.model_copy(
            update={
                "invoice_number": "INV-OTHER",
                "tax": Decimal("536.68"),
                "total": Decimal("3215.08"),
            }
        )
    )

    assert result.reasons == ["All checks passed"]
    assert result.steps[6].outputs == {"duplicates": []}


def test_later_invoice_is_not_an_earlier_duplicate(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    database_url: str,
) -> None:
    later = process_invoice(matching_fields)
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "UPDATE invoices SET created_at = %s WHERE id = %s",
            (datetime.now(UTC) + timedelta(days=1), later.id),
        )

    result = process_invoice(matching_fields)

    assert result.reasons == ["All checks passed"]
    assert result.steps[6].outputs == {"duplicates": []}


@pytest.mark.parametrize("earlier_number", ["INV-MATCH-42", "INV-OTHER"])
def test_duplicate_checks_do_not_cross_suppliers(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    earlier_number: str,
) -> None:
    process_invoice(
        matching_fields.model_copy(
            update={
                "supplier_name": "Northstar Office Supplies",
                "purchase_order_number": None,
                "invoice_number": earlier_number,
            }
        )
    )

    result = process_invoice(matching_fields)

    assert result.reasons == ["All checks passed"]
    assert result.steps[6].outputs == {"duplicates": []}


def test_duplicate_checks_do_not_cross_demo_companies(
    client: TestClient,
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    database_url: str,
    matching_fields: InvoiceFields,
) -> None:
    process_invoice(matching_fields)
    with closing(TestClient(client.app)) as other_visitor:
        company_id = UUID(other_visitor.post("/api/demo-company").json()["id"])
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(matching_fields),
        erp_tools=ERPTools(database_url),
        daily_ai_limit=DailyAILimit(database_url),
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

    assert result.reasons == ["All checks passed"]
    assert result.steps[6].outputs == {"duplicates": []}


def test_every_earlier_duplicate_is_named_and_saved_with_its_record_id(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
) -> None:
    exact = process_invoice(matching_fields)
    possible = process_invoice(
        matching_fields.model_copy(update={"invoice_number": "INV-OTHER"})
    )

    result = process_invoice(matching_fields)

    assert result.reasons == [
        "Duplicate Invoice: INV-MATCH-42 was already received.",
        "Possible Duplicate: INV-OTHER has the same total "
        "and was received within 30 days.",
    ]
    assert result.steps[6].outputs == {
        "duplicates": [
            {
                "invoice_id": str(exact.id),
                "invoice_number": "INV-MATCH-42",
                "reason": "Duplicate Invoice: INV-MATCH-42 was already received.",
            },
            {
                "invoice_id": str(possible.id),
                "invoice_number": "INV-OTHER",
                "reason": "Possible Duplicate: INV-OTHER has the same total "
                "and was received within 30 days.",
            },
        ]
    }
