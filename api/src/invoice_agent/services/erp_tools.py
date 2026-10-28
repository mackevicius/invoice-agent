from datetime import UTC, datetime
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from invoice_agent.schemas.erp_tools import GoodsReceipt, PurchaseOrder, Supplier


class ERPTools:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

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
