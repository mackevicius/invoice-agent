from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb
from pydantic import JsonValue

from invoice_agent.schemas.erp_tools import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from invoice_agent.schemas.invoice_fields import InvoiceFields, InvoiceLine
from invoice_agent.schemas.three_way_match import (
    ComparisonCell,
    LineComparison,
    PairedLine,
)


@dataclass(frozen=True)
class SampleInvoice:
    supplier: str
    number: str
    total: str
    status: Literal["Auto-Approved", "In Review", "Approved", "Rejected"]
    description: str
    quantity: int
    price: str
    invoice_quantity: int | None = None
    invoice_price: str | None = None
    invoice_description: str | None = None
    received_quantity: int | None = None
    known_supplier: bool = True
    paired_by: Literal["description", "meaning"] = "description"
    price_passed: bool = True
    quantity_passed: bool = True
    mismatched_cells: tuple[ComparisonCell, ...] = ()
    line_reasons: tuple[str, ...] = ()
    decision_reasons: tuple[str, ...] = ()
    duplicate_of: tuple[str, ...] = ()
    rejection_reason: str | None = None


SAMPLES = (
    SampleInvoice(
        "Northstar Office Supplies",
        "INV-1042",
        "1344.00",
        "Auto-Approved",
        "Ergonomic keyboards",
        12,
        "112.00",
    ),
    SampleInvoice(
        "Paper & Co.",
        "INV-0309",
        "2760.00",
        "In Review",
        "Recycled A4 paper, box",
        24,
        "111.60",
        invoice_price="115.00",
        price_passed=False,
        mismatched_cells=("invoice.unit_price", "purchase_order.unit_price"),
        line_reasons=(
            "Line 1 (Recycled A4 paper, box): unit price is more than 2% "
            "above the Purchase Order.",
        ),
    ),
    SampleInvoice(
        "Byteworks IT",
        "INV-0781",
        "8640.00",
        "Approved",
        "27-inch monitors",
        8,
        "1080.00",
        decision_reasons=(
            "Invoice total is at or above the Auto-Approval Limit of EUR 5,000.00.",
        ),
    ),
    SampleInvoice(
        "Northstar Office Supplies",
        "INV-1043",
        "512.00",
        "Rejected",
        "Desk organisers",
        16,
        "32.00",
        received_quantity=12,
        quantity_passed=False,
        mismatched_cells=("invoice.quantity", "goods_receipt.quantity"),
        line_reasons=(
            "Line 1 (Desk organisers): invoiced quantity does not equal "
            "received quantity.",
        ),
        rejection_reason="Only 12 desk organisers were received.",
    ),
    SampleInvoice(
        "Baltic Logistics",
        "INV-0217",
        "960.00",
        "In Review",
        "Pallet deliveries",
        10,
        "96.00",
        received_quantity=8,
        quantity_passed=False,
        mismatched_cells=("invoice.quantity", "goods_receipt.quantity"),
        line_reasons=(
            "Line 1 (Pallet deliveries): invoiced quantity does not equal "
            "received quantity.",
        ),
    ),
    SampleInvoice(
        "Northstar Office Supplies",
        "INV-1044",
        "1260.00",
        "Auto-Approved",
        "Ergonomic keyboards",
        12,
        "112.00",
        invoice_price="105.00",
    ),
    SampleInvoice(
        "Baltic Logistics",
        "INV-0218",
        "480.00",
        "Auto-Approved",
        "Pallet deliveries",
        10,
        "96.00",
        invoice_quantity=5,
        received_quantity=5,
    ),
    SampleInvoice(
        "Northstar Office Supplies",
        "INV-1045",
        "896.00",
        "Auto-Approved",
        "Ergonomic keyboards",
        8,
        "112.00",
        invoice_description="Ergonomic computer keyboards",
        paired_by="meaning",
    ),
    SampleInvoice(
        "Byteworks IT",
        "INV-0781",
        "2160.00",
        "In Review",
        "27-inch monitors",
        2,
        "1080.00",
        duplicate_of=("INV-0781",),
        decision_reasons=("Duplicate Invoice: INV-0781 was already received.",),
    ),
    SampleInvoice(
        "Northstar Office Supplies",
        "INV-1046",
        "1260.00",
        "In Review",
        "Ergonomic keyboards",
        12,
        "105.00",
        duplicate_of=("INV-1044",),
        decision_reasons=(
            "Possible Duplicate: INV-1044 has the same total "
            "and was received within 30 days.",
        ),
    ),
    SampleInvoice(
        "Unknown Trading",
        "INV-0001",
        "250.00",
        "In Review",
        "Packing supplies",
        5,
        "50.00",
        known_supplier=False,
        decision_reasons=("Unknown Supplier",),
    ),
    SampleInvoice(
        "Byteworks IT",
        "INV-0782",
        "6480.00",
        "In Review",
        "27-inch monitors",
        6,
        "1080.00",
        decision_reasons=(
            "Invoice total is at or above the Auto-Approval Limit of EUR 5,000.00.",
        ),
    ),
)


def seed_demo_company(
    connection: Connection[tuple[object, ...]],
    company_id: UUID,
    now: datetime,
    embeddings: list[list[float]] | None = None,
    embedding_model: str | None = None,
) -> None:
    suppliers: dict[str, Supplier] = {}
    earlier_invoice_ids: dict[tuple[str, str], UUID] = {}
    for position, sample in enumerate(SAMPLES):
        if sample.known_supplier and sample.supplier not in suppliers:
            suppliers[sample.supplier] = Supplier(id=uuid4(), name=sample.supplier)
            connection.execute(
                "INSERT INTO suppliers (id, company_id, name) VALUES (%s, %s, %s)",
                (suppliers[sample.supplier].id, company_id, sample.supplier),
            )
        supplier = suppliers.get(sample.supplier)
        invoice_id = uuid4()
        created_at = now - (
            timedelta(minutes=len(SAMPLES) - position)
            if position
            else timedelta(seconds=10)
        )
        fields = InvoiceFields(
            supplier_name=sample.supplier,
            invoice_number=sample.number,
            purchase_order_number=f"PO-{1001 + position}",
            issued_on=created_at.date(),
            currency="EUR",
            lines=[
                InvoiceLine(
                    description=sample.invoice_description or sample.description,
                    quantity=Decimal(sample.invoice_quantity or sample.quantity),
                    unit_price=Decimal(sample.invoice_price or sample.price),
                )
            ],
            subtotal=Decimal(sample.total),
            tax=Decimal("0.00"),
            total=Decimal(sample.total),
        )
        steps: list[tuple[str, dict[str, JsonValue], dict[str, JsonValue]]] = [
            (
                "Read Invoice",
                {"filename": f"{sample.number}.pdf", "content_type": "application/pdf"},
                fields.model_dump(mode="json"),
            ),
            (
                "Find Supplier",
                {"name": sample.supplier},
                {"supplier": supplier.model_dump(mode="json") if supplier else None},
            ),
        ]
        comparison: list[JsonValue] = []
        reasons = [*sample.line_reasons, *sample.decision_reasons]
        if supplier is not None:
            purchase_line = PurchaseOrderLine(
                id=uuid4(),
                description=sample.description,
                quantity=Decimal(sample.quantity).quantize(Decimal("0.001")),
                unit_price=Decimal(sample.price),
            )
            purchase = PurchaseOrder(
                id=uuid4(),
                supplier_id=supplier.id,
                number=f"PO-{1001 + position}",
                lines=[purchase_line],
            )
            receipt_id = uuid4()
            receipt = GoodsReceipt(
                purchase_order_id=purchase.id,
                numbers=[f"GR-{2001 + position}"],
                lines=[
                    GoodsReceiptLine(
                        purchase_order_line_id=purchase_line.id,
                        quantity=Decimal(
                            sample.received_quantity or sample.quantity
                        ).quantize(Decimal("0.001")),
                    )
                ],
            )
            connection.execute(
                """INSERT INTO purchase_orders (id, company_id, supplier_id, number)
                   VALUES (%s, %s, %s, %s)""",
                (purchase.id, company_id, supplier.id, purchase.number),
            )
            connection.execute(
                """INSERT INTO purchase_order_lines
                   (id, company_id, purchase_order_id, description, quantity,
                    unit_price, embedding, embedding_model)
                   VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s)""",
                (
                    purchase_line.id,
                    company_id,
                    purchase.id,
                    purchase_line.description,
                    purchase_line.quantity,
                    purchase_line.unit_price,
                    embeddings[position] if embeddings is not None else None,
                    embedding_model,
                ),
            )
            connection.execute(
                """INSERT INTO goods_receipts
                   (id, company_id, purchase_order_id, number)
                   VALUES (%s, %s, %s, %s)""",
                (receipt_id, company_id, purchase.id, receipt.numbers[0]),
            )
            connection.execute(
                """INSERT INTO goods_receipt_lines
                   (id, company_id, goods_receipt_id, purchase_order_line_id, quantity)
                   VALUES (%s, %s, %s, %s, %s)""",
                (
                    uuid4(),
                    company_id,
                    receipt_id,
                    purchase_line.id,
                    receipt.lines[0].quantity,
                ),
            )
            pair = PairedLine(
                line_number=1,
                invoice=fields.lines[0],
                purchase_order=purchase_line,
                paired_by=sample.paired_by,
            )
            difference = fields.lines[0].unit_price - purchase_line.unit_price
            comparison = [
                LineComparison(
                    **pair.model_dump(),
                    goods_receipt=receipt.lines[0],
                    unit_price_difference=difference,
                    unit_price_difference_percent=(
                        difference / purchase_line.unit_price * 100
                    ).quantize(Decimal("0.01")),
                    price_passed=sample.price_passed,
                    quantity_passed=sample.quantity_passed,
                    mismatched_cells=list(sample.mismatched_cells),
                    reasons=list(sample.line_reasons),
                ).model_dump(mode="json")
            ]
            pairs: list[JsonValue] = [pair.model_dump(mode="json")]
            duplicates: list[JsonValue] = [
                {
                    "invoice_id": str(earlier_invoice_ids[(sample.supplier, number)]),
                    "invoice_number": number,
                    "reason": reason,
                }
                for number, reason in zip(
                    sample.duplicate_of,
                    sample.decision_reasons if sample.duplicate_of else (),
                    strict=True,
                )
            ]
            steps.extend(
                [
                    (
                        "Find Purchase Order",
                        {"number": fields.purchase_order_number},
                        {"purchase_order": purchase.model_dump(mode="json")},
                    ),
                    (
                        "Find Goods Receipt",
                        {"purchase_order_id": str(purchase.id)},
                        {"goods_receipt": receipt.model_dump(mode="json")},
                    ),
                    (
                        "Pair Lines",
                        {
                            "invoice_lines": [
                                line.model_dump(mode="json") for line in fields.lines
                            ],
                            "purchase_order_id": str(purchase.id),
                        },
                        {
                            "pairs": pairs,
                            "candidate_searches": [
                                {
                                    "line_number": 1,
                                    "candidates": [
                                        purchase_line.model_dump(mode="json")
                                    ],
                                }
                            ]
                            if sample.paired_by == "meaning"
                            else [],
                            "reasons": [],
                        },
                    ),
                    (
                        "Three-Way Match",
                        {
                            "pairs": pairs,
                            "goods_receipt": receipt.model_dump(mode="json"),
                        },
                        {
                            "passed": sample.price_passed and sample.quantity_passed,
                            "comparison": comparison,
                        },
                    ),
                    (
                        "Check Duplicates",
                        {"supplier_id": str(supplier.id)},
                        {"duplicates": duplicates},
                    ),
                    (
                        "Decide",
                        {
                            "three_way_match_passed": not sample.line_reasons,
                            "duplicate_check_passed": not sample.duplicate_of,
                            "total": str(fields.total),
                            "currency": "EUR",
                            "auto_approval_limit": "5000.00",
                            "auto_approval_currency": "EUR",
                        },
                        {
                            "status": "Auto-Approved"
                            if sample.status == "Auto-Approved"
                            else "In Review",
                            "reasons": [reason for reason in reasons],
                        },
                    ),
                ]
            )
        else:
            steps.extend(
                (name, {}, {"reason": "Unknown Supplier"})
                for name in (
                    "Find Purchase Order",
                    "Find Goods Receipt",
                    "Pair Lines",
                    "Three-Way Match",
                    "Check Duplicates",
                    "Decide",
                )
            )
        connection.execute(
            """INSERT INTO invoices
               (id, company_id, supplier_id, supplier_name, invoice_number, total,
                status, issued_on, created_at, auto_approval_limit, read_fields,
                comparison, reasons, rejection_reason)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                invoice_id,
                company_id,
                supplier.id if supplier else None,
                sample.supplier,
                sample.number,
                fields.total,
                sample.status,
                created_at.date(),
                created_at,
                Decimal("5000.00") if supplier else None,
                Jsonb(fields.model_dump(mode="json")),
                Jsonb(comparison),
                Jsonb(reasons),
                sample.rejection_reason,
            ),
        )
        connection.execute(
            """INSERT INTO invoice_lines
               (id, company_id, invoice_id, description, quantity, unit_price)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                uuid4(),
                company_id,
                invoice_id,
                fields.lines[0].description,
                fields.lines[0].quantity,
                fields.lines[0].unit_price,
            ),
        )
        for step_position, (name, inputs, outputs) in enumerate(steps):
            skipped = supplier is None and step_position > 1
            started_at = created_at + timedelta(seconds=step_position)
            connection.execute(
                """INSERT INTO invoice_steps
                   (company_id, invoice_id, name, position, status, inputs,
                    outputs, started_at, completed_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    company_id,
                    invoice_id,
                    name,
                    step_position,
                    "Skipped" if skipped else "Completed",
                    Jsonb(inputs),
                    Jsonb(outputs),
                    None if skipped else started_at,
                    created_at + timedelta(seconds=2)
                    if skipped
                    else started_at + timedelta(milliseconds=100),
                ),
            )
        earlier_invoice_ids.setdefault((sample.supplier, sample.number), invoice_id)


def configure_decision_receipt(
    connection: Connection[tuple[object, ...]],
    company_id: UUID,
    quantity: Decimal | None,
) -> None:
    if quantity is None:
        connection.execute(
            "DELETE FROM goods_receipt_lines WHERE company_id = %s", (company_id,)
        )
        connection.execute(
            "DELETE FROM goods_receipts WHERE company_id = %s", (company_id,)
        )
    else:
        connection.execute(
            "UPDATE goods_receipt_lines SET quantity = %s WHERE company_id = %s",
            (quantity, company_id),
        )
