from datetime import UTC, datetime
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from invoice_agent.schemas.erp_tools import Supplier


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


def _supplier_key(name: str) -> str:
    return "".join(character for character in name.casefold() if character.isalnum())
