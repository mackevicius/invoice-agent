import os
import subprocess
from contextlib import closing
from datetime import UTC, datetime, timedelta
from threading import Event

import time_machine
from fastapi.testclient import TestClient

from invoice_agent.app import create_app
from invoice_agent.clients.embeddings import ScriptedEmbeddings
from invoice_agent.services.demo_company import DemoCompanies
from invoice_agent.workers.demo_company import InProcessDemoCompanyCleanup


def test_first_visit_starts_a_demo_company_with_seeded_invoices(
    client: TestClient,
) -> None:
    company = client.post("/api/demo-company")

    assert company.status_code == 200
    assert client.cookies.get("demo_company") is not None

    response = client.get("/api/invoices")

    assert response.status_code == 200
    invoices = response.json()
    assert len(invoices) >= 3
    assert invoices[0]["invoice_number"] == "INV-1042"
    assert invoices[0]["supplier"] == "Northstar Office Supplies"
    assert invoices[0]["total"] == "1344.00"
    assert invoices[0]["currency"] == "EUR"
    assert invoices[0]["status"] == "Auto-Approved"


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
