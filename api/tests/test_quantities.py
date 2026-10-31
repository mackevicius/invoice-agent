from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

import psycopg
import pytest

from invoice_agent.schemas.invoice_fields import InvoiceFields
from invoice_agent.schemas.invoices import InvoiceDetail


@pytest.mark.parametrize(
    ("invoiced", "received", "expected_reasons", "expected_cells"),
    [
        ("24", "24", [], []),
        ("6", "6", [], []),
        ("1.250", "1.250", [], []),
        (
            "24",
            "6",
            ["invoiced quantity does not equal received quantity."],
            ["invoice.quantity", "goods_receipt.quantity"],
        ),
        (
            "25",
            "25",
            ["received quantity exceeds the Purchase Order quantity."],
            ["purchase_order.quantity", "goods_receipt.quantity"],
        ),
        (
            "25",
            "26",
            [
                "invoiced quantity does not equal received quantity.",
                "received quantity exceeds the Purchase Order quantity.",
            ],
            [
                "invoice.quantity",
                "purchase_order.quantity",
                "goods_receipt.quantity",
            ],
        ),
    ],
)
def test_quantity_rules_and_partial_deliveries(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    matching_company: UUID,
    database_url: str,
    invoiced: str,
    received: str,
    expected_reasons: list[str],
    expected_cells: list[str],
) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """UPDATE goods_receipt_lines SET quantity = %s
               WHERE company_id = %s""",
            (Decimal(received), matching_company),
        )
    line = matching_fields.lines[0].model_copy(update={"quantity": Decimal(invoiced)})
    fields = matching_fields.model_copy(update={"lines": [line]})

    result = process_invoice(fields)

    assert result.status == ("In Review" if expected_reasons else "Auto-Approved")
    assert result.reasons == [
        f"Line 1 (Recycled A4 paper, box): {reason}" for reason in expected_reasons
    ]
    comparison = result.comparison[0]
    assert comparison.quantity_passed is (not expected_reasons)
    assert comparison.price_passed is True
    assert comparison.goods_receipt is not None
    assert comparison.goods_receipt.quantity == Decimal(received)
    assert set(comparison.mismatched_cells) == set(expected_cells)
