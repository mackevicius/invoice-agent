from collections.abc import Callable
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest

from invoice_agent.schemas.invoice_fields import InvoiceFields, InvoiceLine
from invoice_agent.schemas.invoices import InvoiceDetail


@pytest.mark.parametrize(
    ("item_code", "description", "paired_by"),
    [
        ("PAPER-A4", "Paper supplied in boxes", "item_code"),
        (None, "Recycled A4 paper, box", "description"),
        ("OTHER-ITEM", "Recycled A4 paper, box", None),
        (None, "Extra packing charge", None),
        (None, "Recycled A4 paper", None),
    ],
)
def test_only_clearly_corresponding_lines_are_paired(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    matching_company: UUID,
    database_url: str,
    item_code: str | None,
    description: str,
    paired_by: str | None,
) -> None:
    original = matching_fields.lines[0]
    line = InvoiceLine(
        item_code=item_code,
        description=description,
        quantity=original.quantity,
        unit_price=original.unit_price,
    )
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """UPDATE purchase_order_lines SET item_code = 'PAPER-A4'
               WHERE company_id = %s""",
            (matching_company,),
        )

    result = process_invoice(matching_fields.model_copy(update={"lines": [line]}))

    assert result.status == "In Review"
    comparison = result.comparison[0]
    assert comparison.paired_by == paired_by
    if paired_by is None:
        assert comparison.purchase_order is None
        assert comparison.price_passed is False
        assert comparison.quantity_passed is False
        assert result.reasons == [
            f"Line 1 ({description}): no paired Purchase Order line."
        ]
    else:
        assert comparison.purchase_order is not None
        assert comparison.purchase_order.item_code == "PAPER-A4"
        assert result.reasons == ["All checks passed"]


def test_every_failure_is_reported_across_invoice_lines(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
) -> None:
    overcharged = matching_fields.lines[0].model_copy(
        update={"quantity": Decimal("30"), "unit_price": Decimal("120.00")}
    )
    unpaired = InvoiceLine(
        description="Extra packing charge",
        quantity=Decimal("1"),
        unit_price=Decimal("3.00"),
    )

    result = process_invoice(
        matching_fields.model_copy(update={"lines": [overcharged, unpaired]})
    )

    assert result.status == "In Review"
    assert result.reasons == [
        "Line 1 (Recycled A4 paper, box): unit price is more than 2% "
        "above the Purchase Order.",
        "Line 1 (Recycled A4 paper, box): invoiced quantity does not equal "
        "received quantity.",
        "Line 2 (Extra packing charge): no paired Purchase Order line.",
    ]
    assert len(result.comparison) == 2
    assert result.comparison[1].purchase_order is None
    assert result.comparison[1].goods_receipt is None


def test_identical_description_resolves_a_repeated_item_code(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    matching_company: UUID,
    database_url: str,
) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """UPDATE purchase_order_lines SET item_code = 'SERVICE'
               WHERE company_id = %s""",
            (matching_company,),
        )
        connection.execute(
            """INSERT INTO purchase_order_lines
               (id, company_id, purchase_order_id, item_code,
                description, quantity, unit_price)
               SELECT %s, company_id, id, 'SERVICE', 'Additional paper boxes',
                      24, 111.60
               FROM purchase_orders WHERE company_id = %s AND number = 'PO-1002'""",
            (uuid4(), matching_company),
        )
    line = matching_fields.lines[0].model_copy(update={"item_code": "SERVICE"})

    result = process_invoice(matching_fields.model_copy(update={"lines": [line]}))

    assert result.status == "In Review"
    assert result.reasons == ["All checks passed"]
    assert result.comparison[0].paired_by == "description"
    assert result.comparison[0].purchase_order is not None
    assert result.comparison[0].purchase_order.description == "Recycled A4 paper, box"
