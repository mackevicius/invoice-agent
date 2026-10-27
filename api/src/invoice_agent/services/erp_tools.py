from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import psycopg
from mcp.server.fastmcp import FastMCP
from psycopg.rows import dict_row
from pydantic import Field

from invoice_agent.schemas.erp_tools import FindSupplierResult, Supplier


def create_erp_server(database_url: str, company_id: UUID) -> FastMCP:
    server = FastMCP("Demo Company ERP")

    @server.tool(description="Find a Supplier by name in this Demo Company.")
    def find_supplier_by_name(
        name: Annotated[str, Field(min_length=1, max_length=200)],
    ) -> FindSupplierResult:
        key = _supplier_key(name)
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            suppliers = connection.execute(
                """SELECT supplier.id, supplier.name FROM suppliers AS supplier
                   JOIN demo_companies AS company ON company.id = supplier.company_id
                   WHERE supplier.company_id = %s AND company.expires_at > %s""",
                (company_id, datetime.now(UTC)),
            ).fetchall()
        matches = [
            supplier for supplier in suppliers if _supplier_key(supplier["name"]) == key
        ]
        return FindSupplierResult(
            supplier=Supplier.model_validate(matches[0]) if len(matches) == 1 else None
        )

    return server


def _supplier_key(name: str) -> str:
    return "".join(character for character in name.casefold() if character.isalnum())
