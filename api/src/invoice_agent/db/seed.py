from datetime import datetime, timedelta
from uuid import UUID, uuid4

from psycopg import Connection

SAMPLES = (
    (
        "Northstar Office Supplies",
        "INV-1042",
        "1344.00",
        "Auto-Approved",
        "Ergonomic keyboards",
        12,
        "112.00",
    ),
    (
        "Paper & Co.",
        "INV-0309",
        "2678.40",
        "In Review",
        "Recycled A4 paper, box",
        24,
        "111.60",
    ),
    (
        "Byteworks IT",
        "INV-0781",
        "8640.00",
        "Approved",
        "27-inch monitors",
        8,
        "1080.00",
    ),
    (
        "Northstar Office Supplies",
        "INV-1043",
        "512.00",
        "Rejected",
        "Desk organisers",
        16,
        "32.00",
    ),
    (
        "Baltic Logistics",
        "INV-0217",
        "960.00",
        "In Review",
        "Pallet deliveries",
        10,
        "96.00",
    ),
)


def seed_demo_company(
    connection: Connection[tuple[object, ...]],
    company_id: UUID,
    now: datetime,
    embeddings: list[list[float]] | None = None,
    embedding_model: str | None = None,
) -> None:
    suppliers: dict[str, UUID] = {}
    for position, sample in enumerate(SAMPLES):
        supplier, number, total, status, description, quantity, price = sample
        if supplier not in suppliers:
            suppliers[supplier] = uuid4()
            connection.execute(
                "INSERT INTO suppliers (id, company_id, name) VALUES (%s, %s, %s)",
                (suppliers[supplier], company_id, supplier),
            )

        purchase_id, purchase_line_id, receipt_id, invoice_id = (
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
        )
        connection.execute(
            """INSERT INTO purchase_orders (id, company_id, supplier_id, number)
               VALUES (%s, %s, %s, %s)""",
            (purchase_id, company_id, suppliers[supplier], f"PO-{1001 + position}"),
        )
        connection.execute(
            """INSERT INTO purchase_order_lines
               (id, company_id, purchase_order_id, description, quantity,
                unit_price, embedding, embedding_model)
               VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s)""",
            (
                purchase_line_id,
                company_id,
                purchase_id,
                description,
                quantity,
                price,
                embeddings[position] if embeddings is not None else None,
                embedding_model,
            ),
        )
        connection.execute(
            """INSERT INTO goods_receipts
               (id, company_id, purchase_order_id, number)
               VALUES (%s, %s, %s, %s)""",
            (receipt_id, company_id, purchase_id, f"GR-{2001 + position}"),
        )
        connection.execute(
            """INSERT INTO goods_receipt_lines
               (id, company_id, goods_receipt_id, purchase_order_line_id, quantity)
               VALUES (%s, %s, %s, %s, %s)""",
            (uuid4(), company_id, receipt_id, purchase_line_id, quantity),
        )
        created_at = now - timedelta(minutes=position)
        connection.execute(
            """INSERT INTO invoices
               (id, company_id, supplier_id, supplier_name, invoice_number, total,
                status, issued_on, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                invoice_id,
                company_id,
                suppliers[supplier],
                supplier,
                number,
                total,
                status,
                created_at.date(),
                created_at,
            ),
        )
        connection.execute(
            """INSERT INTO invoice_lines
               (id, company_id, invoice_id, description, quantity, unit_price)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (uuid4(), company_id, invoice_id, description, quantity, price),
        )
