from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

import psycopg
import pytest

from invoice_agent.schemas.invoice_fields import InvoiceFields
from invoice_agent.schemas.invoices import InvoiceDetail


@pytest.mark.parametrize(
    ("unit_price", "price_passed", "difference"),
    [
        ("100.00", True, "0.00"),
        ("102.00", True, "2.00"),
        ("102.01", False, "2.01"),
        ("90.00", True, "-10.00"),
    ],
)
def test_price_tolerance_and_visible_difference(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    matching_company: UUID,
    database_url: str,
    unit_price: str,
    price_passed: bool,
    difference: str,
) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """UPDATE purchase_order_lines SET unit_price = 100
               WHERE company_id = %s""",
            (matching_company,),
        )
    line = matching_fields.lines[0].model_copy(
        update={"unit_price": Decimal(unit_price)}
    )
    fields = matching_fields.model_copy(update={"lines": [line]})

    result = process_invoice(fields)

    assert result.status == "In Review"
    assert result.reasons == (
        ["All checks passed"]
        if price_passed
        else [
            "Line 1 (Recycled A4 paper, box): unit price is more than 2% "
            "above the Purchase Order."
        ]
    )
    comparison = result.comparison[0]
    assert comparison.price_passed is price_passed
    assert comparison.quantity_passed is True
    assert comparison.unit_price_difference == Decimal(difference)
    assert comparison.unit_price_difference_percent == Decimal(difference)
    assert comparison.purchase_order is not None
    assert comparison.purchase_order.unit_price == Decimal("100.00")
    assert [step.status for step in result.steps[:6]] == ["Completed"] * 6
    assert result.steps[6].status == "Completed"
    assert result.steps[7].name == "Decide"
    assert result.steps[7].status == "Completed"
