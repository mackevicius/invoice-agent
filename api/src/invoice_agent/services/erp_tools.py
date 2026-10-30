from datetime import UTC, datetime
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from invoice_agent.clients.embeddings import TextEmbeddings
from invoice_agent.schemas.erp_tools import (
    EarlierInvoice,
    GoodsReceipt,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)


class ERPTools:
    def __init__(
        self, database_url: str, embeddings: TextEmbeddings | None = None
    ) -> None:
        self.database_url = database_url
        self.embeddings = embeddings

    def index_purchase_order_lines(self) -> None:
        if self.embeddings is None:
            return
        with psycopg.connect(self.database_url) as connection:
            lines = connection.execute(
                """SELECT id, company_id, description FROM purchase_order_lines
                   WHERE embedding IS NULL OR embedding_model IS DISTINCT FROM %s
                   ORDER BY id""",
                (self.embeddings.model_name,),
            ).fetchall()
            if not lines:
                return
            vectors = self.embeddings.embed([str(line[2]) for line in lines])
            for line, vector in zip(lines, vectors, strict=True):
                connection.execute(
                    """UPDATE purchase_order_lines SET embedding = %s::vector,
                                        embedding_model = %s
                       WHERE id = %s AND company_id = %s""",
                    (vector, self.embeddings.model_name, line[0], line[1]),
                )

    def find_supplier(self, company_id: UUID, name: str) -> Supplier | None:
        key = _supplier_key(name)
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            suppliers = connection.execute(
                """SELECT supplier.id, supplier.name FROM suppliers AS supplier
                   JOIN demo_companies AS company ON company.id = supplier.company_id
                   WHERE supplier.company_id = %s AND company.expires_at > %s""",
                (company_id, datetime.now(UTC)),
            ).fetchall()
        matches = [
            supplier for supplier in suppliers if _supplier_key(supplier["name"]) == key
        ]
        return Supplier.model_validate(matches[0]) if len(matches) == 1 else None

    def find_earlier_invoices(
        self, company_id: UUID, supplier_id: UUID, invoice_id: UUID
    ) -> list[EarlierInvoice]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            invoices = connection.execute(
                """SELECT earlier.id, earlier.invoice_number, earlier.total,
                                  earlier.created_at AS received_at
                   FROM invoices AS earlier
                   JOIN invoices AS current_invoice
                     ON current_invoice.company_id = earlier.company_id
                   JOIN demo_companies AS company ON company.id = earlier.company_id
                   WHERE earlier.company_id = %s AND earlier.supplier_id = %s
                     AND current_invoice.id = %s AND earlier.id <> current_invoice.id
                     AND earlier.created_at <= current_invoice.created_at
                     AND earlier.invoice_number IS NOT NULL
                     AND company.expires_at > %s
                   ORDER BY earlier.created_at, earlier.id""",
                (company_id, supplier_id, invoice_id, datetime.now(UTC)),
            ).fetchall()
        return [EarlierInvoice.model_validate(invoice) for invoice in invoices]

    def get_purchase_order(
        self, company_id: UUID, supplier_id: UUID, number: str
    ) -> PurchaseOrder | None:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            purchase_order = connection.execute(
                """SELECT purchase.id, purchase.supplier_id, purchase.number
                   FROM purchase_orders AS purchase
                   JOIN demo_companies AS company ON company.id = purchase.company_id
                   WHERE purchase.company_id = %s AND purchase.supplier_id = %s
                     AND purchase.number = %s AND company.expires_at > %s""",
                (company_id, supplier_id, number, datetime.now(UTC)),
            ).fetchone()
            if purchase_order is None:
                return None
            lines = connection.execute(
                """SELECT id, item_code, description, quantity, unit_price
                   FROM purchase_order_lines
                   WHERE company_id = %s AND purchase_order_id = %s ORDER BY id""",
                (company_id, purchase_order["id"]),
            ).fetchall()
        return PurchaseOrder.model_validate({**purchase_order, "lines": lines})

    def search_purchase_order_lines(
        self,
        company_id: UUID,
        purchase_order_id: UUID,
        description: str,
        *,
        item_code: str | None = None,
        excluded_ids: tuple[UUID, ...] = (),
    ) -> list[PurchaseOrderLine]:
        if self.embeddings is None:
            raise RuntimeError("Purchase Order line embeddings are not configured.")
        vector = self.embeddings.embed([description])[0]
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            lines = connection.execute(
                """SELECT line.id, line.item_code, line.description,
                          line.quantity, line.unit_price
                   FROM purchase_order_lines AS line
                   JOIN demo_companies AS company ON company.id = line.company_id
                   WHERE line.company_id = %s AND line.purchase_order_id = %s
                     AND company.expires_at > %s AND line.embedding IS NOT NULL
                                         AND line.embedding_model = %s
                     AND NOT (line.id = ANY(%s::uuid[]))
                     AND (%s::text IS NULL OR line.item_code IS NULL
                          OR line.item_code = %s)
                   ORDER BY line.embedding <=> %s::vector, line.id LIMIT 5""",
                (
                    company_id,
                    purchase_order_id,
                    datetime.now(UTC),
                    self.embeddings.model_name,
                    list(excluded_ids),
                    item_code,
                    item_code,
                    vector,
                ),
            ).fetchall()
        return [PurchaseOrderLine.model_validate(line) for line in lines]

    def get_goods_receipt(
        self, company_id: UUID, purchase_order_id: UUID
    ) -> GoodsReceipt | None:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            receipts = connection.execute(
                """SELECT receipt.number FROM goods_receipts AS receipt
                   JOIN demo_companies AS company ON company.id = receipt.company_id
                   WHERE receipt.company_id = %s AND receipt.purchase_order_id = %s
                     AND company.expires_at > %s ORDER BY receipt.number""",
                (company_id, purchase_order_id, datetime.now(UTC)),
            ).fetchall()
            if not receipts:
                return None
            lines = connection.execute(
                """SELECT line.purchase_order_line_id, SUM(line.quantity) AS quantity
                   FROM goods_receipt_lines AS line
                   JOIN goods_receipts AS receipt
                     ON receipt.company_id = line.company_id
                    AND receipt.id = line.goods_receipt_id
                   WHERE receipt.company_id = %s AND receipt.purchase_order_id = %s
                   GROUP BY line.purchase_order_line_id
                   ORDER BY line.purchase_order_line_id""",
                (company_id, purchase_order_id),
            ).fetchall()
        return GoodsReceipt.model_validate(
            {
                "purchase_order_id": purchase_order_id,
                "numbers": [receipt["number"] for receipt in receipts],
                "lines": lines,
            }
        )


def _supplier_key(name: str) -> str:
    return "".join(character for character in name.casefold() if character.isalnum())
