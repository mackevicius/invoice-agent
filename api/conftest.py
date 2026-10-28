from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from datetime import date
from decimal import Decimal
from time import monotonic, sleep
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo

if TYPE_CHECKING:
    from invoice_agent.schemas.demo_company import DemoRole
    from invoice_agent.schemas.invoice_fields import InvoiceFields
    from invoice_agent.schemas.invoices import InvoiceDetail
    from invoice_agent.services.erp_tools import ERPTools


@pytest.fixture
def erp_tools(database_url: str) -> ERPTools:
    from invoice_agent.services.erp_tools import ERPTools

    return ERPTools(database_url)


@pytest.fixture
def matching_company(client: TestClient) -> UUID:
    return UUID(client.post("/api/demo-company").json()["id"])


@pytest.fixture
def matching_fields() -> InvoiceFields:
    from invoice_agent.schemas.invoice_fields import InvoiceFields, InvoiceLine

    return InvoiceFields(
        supplier_name="Paper & Co.",
        invoice_number="INV-MATCH-42",
        purchase_order_number="PO-1002",
        issued_on=date(2026, 10, 20),
        currency="EUR",
        lines=[
            InvoiceLine(
                description="Recycled A4 paper, box",
                quantity=Decimal("24"),
                unit_price=Decimal("111.60"),
            )
        ],
        subtotal=Decimal("2678.40"),
        tax=Decimal("0"),
        total=Decimal("2678.40"),
    )


@pytest.fixture
def process_invoice(
    matching_company: UUID, database_url: str, erp_tools: ERPTools
) -> Callable[[InvoiceFields], InvoiceDetail]:
    from invoice_agent.clients.invoice_reader import ScriptedInvoiceReader
    from invoice_agent.schemas.invoices import InvoiceFile
    from invoice_agent.services.daily_ai_limit import DailyAILimit
    from invoice_agent.services.invoices import InvoiceProcessing

    def process(fields: InvoiceFields) -> InvoiceDetail:
        processing = InvoiceProcessing(
            database_url,
            reader=ScriptedInvoiceReader(fields),
            erp_tools=erp_tools,
            daily_ai_limit=DailyAILimit(database_url),
        )
        uploaded = processing.upload(
            matching_company,
            InvoiceFile(
                filename="invoice.pdf",
                content_type="application/pdf",
                content=b"%PDF-1.4\nInvoice",
            ),
        )
        result = processing.process(matching_company, uploaded.id)
        assert processing.get(matching_company, uploaded.id) == result
        return result

    return process


@pytest.fixture
def upload_for_review(
    client: TestClient,
) -> Callable[[DemoRole], InvoiceDetail]:
    from invoice_agent.schemas.invoices import InvoiceDetail

    client.post("/api/demo-company")

    def upload(role: DemoRole) -> InvoiceDetail:
        response = client.post(
            "/api/invoices",
            headers={"X-Demo-Role": role},
            files={"file": ("invoice.pdf", b"%PDF-1.4\nInvoice", "application/pdf")},
        )
        assert response.status_code == 202
        invoice_id = response.json()["id"]
        deadline = monotonic() + 5
        while monotonic() < deadline:
            invoice = InvoiceDetail.model_validate(
                client.get(f"/api/invoices/{invoice_id}").json()
            )
            if invoice.status == "In Review" and all(
                step.status not in {"Pending", "Running"} for step in invoice.steps
            ):
                return invoice
            sleep(0.01)
        pytest.fail("Invoice processing did not finish.")

    return upload


@pytest.fixture
def database_url() -> Iterator[str]:
    base_url = os.environ["TEST_DATABASE_URL"]
    schema = f"test_{uuid4().hex}"
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            yield make_conninfo(base_url, options=f"-c search_path={schema},public")
        finally:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    from invoice_agent.app import create_app
    from invoice_agent.clients.invoice_reader import ScriptedInvoiceReader

    with TestClient(
        create_app(
            database_url=database_url,
            cookie_secure=False,
            reader=ScriptedInvoiceReader(None),
        )
    ) as test_client:
        yield test_client
