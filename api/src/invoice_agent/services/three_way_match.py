from decimal import Decimal
from uuid import UUID

from invoice_agent.schemas.erp_tools import GoodsReceipt, PurchaseOrder
from invoice_agent.schemas.invoice_fields import InvoiceLine
from invoice_agent.schemas.three_way_match import (
    ComparisonCell,
    LineComparison,
    PairedLine,
)


def pair_lines(
    invoice_lines: list[InvoiceLine], purchase_order: PurchaseOrder
) -> list[PairedLine]:
    pairs = []
    used: set[UUID] = set()
    for line_number, invoice_line in enumerate(invoice_lines, start=1):
        code_candidates = [
            line
            for line in purchase_order.lines
            if invoice_line.item_code is not None
            and line.item_code == invoice_line.item_code
        ]
        candidates = code_candidates
        if len(code_candidates) != 1:
            candidates = [
                line
                for line in (code_candidates or purchase_order.lines)
                if line.description == invoice_line.description
                and (
                    invoice_line.item_code is None
                    or line.item_code is None
                    or line.item_code == invoice_line.item_code
                )
            ]
        paired = (
            candidates[0]
            if len(candidates) == 1 and candidates[0].id not in used
            else None
        )
        if paired is not None:
            used.add(paired.id)
        pairs.append(
            PairedLine(
                line_number=line_number,
                invoice=invoice_line,
                purchase_order=paired,
                paired_by=("item_code" if len(code_candidates) == 1 else "description")
                if paired is not None
                else None,
            )
        )
    return pairs


def compare_lines(
    pairs: list[PairedLine], goods_receipt: GoodsReceipt | None
) -> list[LineComparison]:
    received = {
        line.purchase_order_line_id: line
        for line in (goods_receipt.lines if goods_receipt is not None else [])
    }
    comparison = []
    for pair in pairs:
        purchase = pair.purchase_order
        receipt = received.get(purchase.id) if purchase is not None else None
        prefix = f"Line {pair.line_number} ({pair.invoice.description}): "
        reasons = []
        mismatched_cells: list[ComparisonCell] = []
        difference = None
        percent = None
        price_passed = False
        quantity_passed = receipt is not None
        if purchase is None:
            reasons.append(
                pair.pairing_reason or prefix + "no paired Purchase Order line."
            )
            mismatched_cells.extend(
                ["invoice.description", "purchase_order.description"]
            )
        else:
            difference = pair.invoice.unit_price - purchase.unit_price
            if purchase.unit_price != 0:
                percent = (difference / purchase.unit_price * 100).quantize(
                    Decimal("0.01")
                )
            price_passed = pair.invoice.unit_price <= purchase.unit_price * Decimal(
                "1.02"
            )
            if not price_passed:
                reasons.append(
                    prefix + "unit price is more than 2% above the Purchase Order."
                )
                mismatched_cells.extend(
                    ["invoice.unit_price", "purchase_order.unit_price"]
                )
            if receipt is None:
                if goods_receipt is not None:
                    reasons.append(prefix + "no Goods Receipt line was found.")
                mismatched_cells.extend(["invoice.quantity", "goods_receipt.quantity"])
            else:
                invoiced_matches_received = pair.invoice.quantity == receipt.quantity
                received_within_order = receipt.quantity <= purchase.quantity
                quantity_passed = invoiced_matches_received and received_within_order
                if not invoiced_matches_received:
                    reasons.append(
                        prefix + "invoiced quantity does not equal received quantity."
                    )
                    mismatched_cells.append("invoice.quantity")
                if not received_within_order:
                    reasons.append(
                        prefix
                        + "received quantity exceeds the Purchase Order quantity."
                    )
                    mismatched_cells.append("purchase_order.quantity")
                if not quantity_passed:
                    mismatched_cells.append("goods_receipt.quantity")
        comparison.append(
            LineComparison(
                **pair.model_dump(),
                goods_receipt=receipt,
                unit_price_difference=difference,
                unit_price_difference_percent=percent,
                price_passed=price_passed,
                quantity_passed=quantity_passed,
                mismatched_cells=mismatched_cells,
                reasons=reasons,
            )
        )
    return comparison
