import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from mcp import ClientSession

from invoice_agent.schemas.erp_tools import FindSupplierResult, Supplier


class ERPTools:
    def __init__(
        self,
        connect: Callable[[UUID], AbstractAsyncContextManager[ClientSession]],
    ) -> None:
        self.connect = connect

    def find_supplier(self, company_id: UUID, name: str) -> Supplier | None:
        return asyncio.run(self._find_supplier(company_id, name))

    async def _find_supplier(self, company_id: UUID, name: str) -> Supplier | None:
        async with self.connect(company_id) as session:
            result = await session.call_tool("find_supplier_by_name", {"name": name})
            if result.isError:
                raise RuntimeError("ERP Supplier lookup failed.")
            return FindSupplierResult.model_validate(result.structuredContent).supplier
