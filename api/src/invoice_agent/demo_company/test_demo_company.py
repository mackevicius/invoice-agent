from datetime import UTC, datetime

import time_machine
from fastapi.testclient import TestClient


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
