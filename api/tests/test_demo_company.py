import os
import subprocess
from contextlib import closing
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Event
from uuid import UUID

import pytest
import time_machine
from fastapi.testclient import TestClient

from invoice_agent.app import create_app
from invoice_agent.clients.embeddings import ScriptedEmbeddings
from invoice_agent.clients.invoice_reader import ScriptedInvoiceReader
from invoice_agent.clients.line_pairing import ScriptedLinePairer
from invoice_agent.schemas.erp_tools import PurchaseOrderLine
from invoice_agent.schemas.invoice_fields import InvoiceFields, InvoiceLine
from invoice_agent.schemas.invoices import InvoiceDetail, InvoiceFile
from invoice_agent.services.daily_ai_limit import DailyAILimit
from invoice_agent.services.demo_company import DemoCompanies
from invoice_agent.services.erp_tools import ERPTools
from invoice_agent.services.invoice_processing import InvoiceProcessing
from invoice_agent.workers.demo_company import InProcessDemoCompanyCleanup


class UnexpectedLiveModel:
    def __init__(self) -> None:
        self.calls: list[str] = []

    @property
    def uses_live_model(self) -> bool:
        return True

    def read(self, document: InvoiceFile) -> InvoiceFields | None:
        self.calls.append("Read Invoice")
        raise AssertionError("Sample browsing must not read an Invoice with a model.")

    def choose(
        self, invoice_line: InvoiceLine, candidates: list[PurchaseOrderLine]
    ) -> UUID | None:
        self.calls.append("Pair Lines")
        raise AssertionError("Sample browsing must not pair lines with a model.")


def test_first_visit_starts_a_demo_company_with_seeded_invoices(
    client: TestClient,
) -> None:
    company = client.post("/api/demo-company")

    assert company.status_code == 200
    assert client.cookies.get("demo_company") is not None

    response = client.get("/api/invoices")

    assert response.status_code == 200
    invoices = response.json()
    assert len(invoices) == 12
    assert invoices[0]["invoice_number"] == "INV-1042"
    assert invoices[0]["supplier"] == "Northstar Office Supplies"
    assert invoices[0]["total"] == "1344.00"
    assert invoices[0]["currency"] == "EUR"
    assert invoices[0]["status"] == "Auto-Approved"


def test_sample_invoices_have_saved_fields_steps_and_decisions(
    client: TestClient,
) -> None:
    client.post("/api/demo-company")

    for header in client.get("/api/invoices").json():
        response = client.get(f"/api/invoices/{header['id']}")

        assert response.status_code == 200
        invoice = response.json()
        assert invoice["fields"] is not None, header["invoice_number"]
        assert invoice["fields"]["total"] == invoice["total"]
        assert [step["name"] for step in invoice["steps"]] == [
            "Read Invoice",
            "Find Supplier",
            "Find Purchase Order",
            "Find Goods Receipt",
            "Pair Lines",
            "Three-Way Match",
            "Check Duplicates",
            "Decide",
        ]
        assert all(
            step["status"] in {"Completed", "Skipped"}
            and step["outputs"] is not None
            and step["completed_at"] is not None
            for step in invoice["steps"]
        )
        assert invoice["steps"][0]["outputs"] == invoice["fields"]
        if invoice["steps"][-1]["status"] == "Completed":
            assert invoice["auto_approval_limit"] == "5000.00"
        if invoice["status"] in {"In Review", "Rejected"}:
            assert invoice["reasons"]


@pytest.mark.parametrize(
    (
        "number",
        "ordered_quantity",
        "invoiced_quantity",
        "ordered_price",
        "price",
        "paired_by",
    ),
    [
        ("INV-1044", "12", "12", "112.00", "105.00", "description"),
        ("INV-0218", "10", "5", "96.00", "96.00", "description"),
        ("INV-1045", "8", "8", "112.00", "112.00", "meaning"),
    ],
    ids=["lower-price", "partial-delivery", "paired-by-meaning"],
)
def test_samples_show_passing_price_quantity_and_wording_differences(
    client: TestClient,
    number: str,
    ordered_quantity: str,
    invoiced_quantity: str,
    ordered_price: str,
    price: str,
    paired_by: str,
) -> None:
    client.post("/api/demo-company")
    header = next(
        invoice
        for invoice in client.get("/api/invoices").json()
        if invoice["invoice_number"] == number
    )
    invoice = InvoiceDetail.model_validate(
        client.get(f"/api/invoices/{header['id']}").json()
    )
    comparison = invoice.comparison[0]

    assert invoice.status == "Auto-Approved"
    assert comparison.purchase_order is not None
    assert comparison.goods_receipt is not None
    assert comparison.purchase_order.quantity == Decimal(ordered_quantity)
    assert comparison.invoice.quantity == Decimal(invoiced_quantity)
    assert comparison.goods_receipt.quantity == Decimal(invoiced_quantity)
    assert comparison.purchase_order.unit_price == Decimal(ordered_price)
    assert comparison.invoice.unit_price == Decimal(price)
    assert comparison.paired_by == paired_by
    if paired_by == "meaning":
        assert comparison.invoice.description != comparison.purchase_order.description


@pytest.mark.parametrize(
    ("number", "status"),
    [
        ("INV-1042", "Auto-Approved"),
        ("INV-0309", "In Review"),
        ("INV-0781", "Approved"),
        ("INV-1043", "Rejected"),
        ("INV-0217", "In Review"),
        ("INV-1044", "Auto-Approved"),
        ("INV-0218", "Auto-Approved"),
        ("INV-1045", "Auto-Approved"),
        ("INV-0781", "In Review"),
        ("INV-1046", "In Review"),
        ("INV-0001", "In Review"),
        ("INV-0782", "In Review"),
    ],
    ids=[
        "clean-auto-approval",
        "price-over-two-percent",
        "reviewer-approved",
        "reviewer-rejected",
        "quantity-mismatch",
        "lower-price",
        "partial-delivery",
        "paired-by-meaning",
        "duplicate-invoice",
        "possible-duplicate",
        "unknown-supplier",
        "total-over-limit",
    ],
)
def test_sample_decisions_and_saved_steps_match_current_rules(
    client: TestClient,
    database_url: str,
    erp_tools: ERPTools,
    number: str,
    status: str,
) -> None:
    company_id = UUID(client.post("/api/demo-company").json()["id"])
    header = next(
        invoice
        for invoice in client.get("/api/invoices").json()
        if invoice["invoice_number"] == number and invoice["status"] == status
    )
    saved = InvoiceDetail.model_validate(
        client.get(f"/api/invoices/{header['id']}").json()
    )
    assert saved.fields is not None
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(saved.fields),
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
        line_pairer=ScriptedLinePairer(
            {
                line.invoice.description: line.purchase_order.id
                for line in saved.comparison
                if line.paired_by == "meaning" and line.purchase_order is not None
            }
        ),
    )

    with time_machine.travel(saved.received_at - timedelta(microseconds=1), tick=False):
        uploaded = processing.upload(
            company_id,
            InvoiceFile(
                filename=f"{number}.pdf",
                content_type="application/pdf",
                content=b"%PDF-1.4\nInvoice",
            ),
        )
        current = processing.process(company_id, uploaded.id)

    expected_status = "In Review" if status in {"Approved", "Rejected"} else status
    assert current.status == expected_status
    assert current.reasons == saved.reasons
    assert current.comparison == saved.comparison
    assert current.auto_approval_limit == saved.auto_approval_limit
    for current_step, saved_step in zip(current.steps, saved.steps, strict=True):
        assert current_step.name == saved_step.name
        assert current_step.status == saved_step.status
        assert current_step.inputs == saved_step.inputs, current_step.name
        assert current_step.outputs == saved_step.outputs, current_step.name


def test_starting_and_browsing_samples_never_calls_a_live_model(
    database_url: str,
    embeddings: ScriptedEmbeddings,
) -> None:
    model = UnexpectedLiveModel()
    with TestClient(
        create_app(
            database_url=database_url,
            cookie_secure=False,
            reader=model,
            line_pairer=model,
            embeddings=embeddings,
        )
    ) as visitor:
        company = visitor.post("/api/demo-company")
        assert company.status_code == 200
        for role in ("Submitter", "Reviewer", "Admin"):
            headers = {"X-Demo-Role": role}
            assert (
                visitor.get("/api/invoices/counts", headers=headers).status_code == 200
            )
            for view in ("all", "mine", "review-queue", "done"):
                response = visitor.get(
                    "/api/invoices", params={"view": view}, headers=headers
                )
                assert response.status_code == 200
                for invoice in response.json():
                    detail = visitor.get(
                        f"/api/invoices/{invoice['id']}", headers=headers
                    )
                    assert detail.status_code == 200
                    assert all(
                        step["status"] in {"Completed", "Skipped"}
                        for step in detail.json()["steps"]
                    )
        assert visitor.post("/api/demo-company").json() == company.json()
        assert model.calls == []


def test_returning_visit_resumes_the_same_demo_company_and_invoices(
    client: TestClient,
) -> None:
    first_company = client.post("/api/demo-company").json()
    first_invoices = client.get("/api/invoices").json()

    returning_company = client.post("/api/demo-company")

    assert returning_company.status_code == 200
    assert returning_company.json() == first_company
    assert client.get("/api/invoices").json() == first_invoices


def test_expired_demo_company_cannot_be_read_and_is_replaced(
    client: TestClient,
) -> None:
    with time_machine.travel(datetime(2026, 10, 26, 12, tzinfo=UTC), tick=False):
        first_company = client.post("/api/demo-company").json()
        first_invoices = client.get("/api/invoices").json()
        token = client.cookies.get("demo_company")

    assert first_company["expires_at"] == "2026-10-27T12:00:00Z"

    with time_machine.travel(datetime(2026, 10, 27, 12, tzinfo=UTC), tick=False):
        expired_cookie = {"Cookie": f"demo_company={token}"}
        assert client.get("/api/invoices", headers=expired_cookie).status_code == 401

        replacement = client.post("/api/demo-company", headers=expired_cookie)

        assert replacement.status_code == 200
        assert replacement.json()["id"] != first_company["id"]
        assert len(client.get("/api/invoices").json()) >= 3
        assert client.get(f"/api/invoices/{first_invoices[0]['id']}").status_code == 404


def test_cleanup_removes_only_expired_demo_companies(
    client: TestClient,
    database_url: str,
) -> None:
    companies = DemoCompanies(database_url)
    with closing(TestClient(client.app)) as newer_visitor:
        with time_machine.travel(datetime(2026, 10, 26, 12, tzinfo=UTC), tick=False):
            client.post("/api/demo-company")
            expired_upload = client.post(
                "/api/invoices",
                files={
                    "file": ("expired.pdf", b"%PDF-1.4\nExpired", "application/pdf")
                },
            )
            assert expired_upload.status_code == 202
            expired_file = f"/api/invoices/{expired_upload.json()['id']}/file"
            assert client.get(expired_file).status_code == 200

        with time_machine.travel(datetime(2026, 10, 27, 11, tzinfo=UTC), tick=False):
            newer_company = newer_visitor.post("/api/demo-company").json()
            newer_upload = newer_visitor.post(
                "/api/invoices",
                files={"file": ("newer.pdf", b"%PDF-1.4\nNewer", "application/pdf")},
            )
            assert newer_upload.status_code == 202
            newer_file = f"/api/invoices/{newer_upload.json()['id']}/file"

        with time_machine.travel(datetime(2026, 10, 27, 12, tzinfo=UTC), tick=False):
            assert companies.cleanup_expired() == 1
            assert companies.cleanup_expired() == 0
            assert client.get("/api/invoices").status_code == 401
            assert client.get(expired_file).status_code == 401
            assert newer_visitor.post("/api/demo-company").json() == newer_company
            assert newer_visitor.get("/api/invoices").status_code == 200
            assert newer_visitor.get(newer_file).content == b"%PDF-1.4\nNewer"


def test_app_startup_removes_expired_companies_without_a_returning_visitor(
    client: TestClient,
    database_url: str,
    embeddings: ScriptedEmbeddings,
) -> None:
    with time_machine.travel(datetime(2026, 10, 26, 12, tzinfo=UTC), tick=False):
        client.post("/api/demo-company")

    with time_machine.travel(datetime(2026, 10, 27, 12, tzinfo=UTC), tick=False):
        with TestClient(create_app(database_url=database_url, embeddings=embeddings)):
            assert DemoCompanies(database_url).cleanup_expired() == 0


def test_scheduled_cleanup_runs_without_an_http_request(
    client: TestClient,
    database_url: str,
) -> None:
    companies = DemoCompanies(database_url)
    cleanup = InProcessDemoCompanyCleanup(companies, interval_seconds=0.01)

    with time_machine.travel(
        datetime(2026, 10, 26, 12, tzinfo=UTC), tick=False
    ) as clock:
        client.post("/api/demo-company")
        cleanup.start()
        try:
            clock.shift(timedelta(hours=24))
            Event().wait(1)
        finally:
            cleanup.close()

        assert companies.cleanup_expired() == 0


def test_cleanup_command_removes_expired_companies(
    client: TestClient,
    database_url: str,
) -> None:
    with time_machine.travel(datetime.now(UTC) - timedelta(days=2), tick=False):
        client.post("/api/demo-company")

    result = subprocess.run(
        ["invoice-agent-cleanup"],
        env=os.environ | {"DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    assert result.stdout.strip() == "Removed 1 expired Demo Companies."
    assert DemoCompanies(database_url).cleanup_expired() == 0
