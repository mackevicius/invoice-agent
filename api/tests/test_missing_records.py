from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

import psycopg
import pytest

from invoice_agent.schemas.invoice_fields import InvoiceFields, InvoiceLine
from invoice_agent.schemas.invoices import InvoiceDetail


def test_invoice_without_purchase_order_reference_goes_in_review(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
) -> None:
    result = process_invoice(
        matching_fields.model_copy(update={"purchase_order_number": None})
    )

    assert result.status == "In Review"
    assert result.reasons == ["No Purchase Order is named on this Invoice."]


@pytest.mark.parametrize("number", ["PO-NOT-FOUND", "PO-1001"])
def test_missing_or_different_supplier_purchase_order_goes_in_review(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    number: str,
) -> None:
    fields = matching_fields.model_copy(update={"purchase_order_number": number})

    result = process_invoice(fields)

    assert result.status == "In Review"
    assert result.reasons == [
        f"Purchase Order {number} was not found for this Supplier."
    ]
    assert result.steps[2].name == "Find Purchase Order"
    assert result.steps[2].status == "Completed"
    assert result.steps[2].outputs == {"purchase_order": None}
    assert all(step.status == "Skipped" for step in result.steps[3:])


def test_missing_goods_receipt_goes_in_review(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    matching_company: UUID,
    database_url: str,
) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "DELETE FROM goods_receipt_lines WHERE company_id = %s",
            (matching_company,),
        )
        connection.execute(
            "DELETE FROM goods_receipts WHERE company_id = %s", (matching_company,)
        )

    result = process_invoice(matching_fields)

    assert result.status == "In Review"
    assert result.reasons == ["No Goods Receipt was found for Purchase Order PO-1002."]
    assert result.steps[2].status == "Completed"
    assert result.steps[3].name == "Find Goods Receipt"
    assert result.steps[3].status == "Completed"
    assert result.steps[3].outputs == {"goods_receipt": None}
    assert [step.status for step in result.steps[4:]] == [
        "Completed",
        "Completed",
        "Skipped",
        "Completed",
    ]
    assert result.comparison[0].price_passed is True
    assert result.comparison[0].quantity_passed is False


def test_missing_receipt_does_not_hide_price_or_unpaired_line_failures(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    matching_company: UUID,
    database_url: str,
) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "DELETE FROM goods_receipt_lines WHERE company_id = %s",
            (matching_company,),
        )
        connection.execute(
            "DELETE FROM goods_receipts WHERE company_id = %s", (matching_company,)
        )
    overcharged = matching_fields.lines[0].model_copy(
        update={"unit_price": Decimal("120.00")}
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
        "No Goods Receipt was found for Purchase Order PO-1002.",
        "Line 1 (Recycled A4 paper, box): unit price is more than 2% "
        "above the Purchase Order.",
        "Line 2 (Extra packing charge): no paired Purchase Order line.",
    ]
    assert len(result.comparison) == 2
    assert all(line.goods_receipt is None for line in result.comparison)
