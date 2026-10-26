from contextlib import closing

import pytest
from fastapi.testclient import TestClient


def test_demo_company_and_invoice_responses_cannot_be_cached(
    client: TestClient,
) -> None:
    company = client.post("/api/demo-company")
    invoices = client.get("/api/invoices")
    invoice = client.get(f"/api/invoices/{invoices.json()[0]['id']}")

    for response in (company, invoices, invoice):
        assert "no-store" in response.headers.get("cache-control", "")


def test_visitors_cannot_list_or_fetch_each_others_invoices(
    client: TestClient,
) -> None:
    client.post("/api/demo-company")
    uploaded = client.post(
        "/api/invoices",
        files={"file": ("invoice.pdf", b"%PDF-1.4\nInvoice", "application/pdf")},
    )
    assert uploaded.status_code == 202
    own_invoices = client.get("/api/invoices").json()
    assert own_invoices[0]["id"] == uploaded.json()["id"]

    with closing(TestClient(client.app)) as other_visitor:
        other_visitor.post("/api/demo-company")
        other_invoices = other_visitor.get("/api/invoices").json()

        assert {invoice["id"] for invoice in own_invoices}.isdisjoint(
            invoice["id"] for invoice in other_invoices
        )
        assert (
            other_visitor.get(f"/api/invoices/{own_invoices[0]['id']}").status_code
            == 404
        )
        assert client.get(f"/api/invoices/{other_invoices[0]['id']}").status_code == 404


@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_invoice_requests_require_a_valid_session(
    client: TestClient,
    token: str | None,
) -> None:
    headers = {"Cookie": f"demo_company={token}"} if token is not None else {}

    assert client.get("/api/invoices", headers=headers).status_code == 401
    assert (
        client.post(
            "/api/invoices",
            files={"file": ("invoice.pdf", b"%PDF-1.4\nInvoice", "application/pdf")},
            headers=headers,
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/invoices/00000000-0000-0000-0000-000000000001", headers=headers
        ).status_code
        == 401
    )


def test_company_id_is_not_a_session_credential(client: TestClient) -> None:
    company_id = client.post("/api/demo-company").json()["id"]

    response = client.get(
        "/api/invoices", headers={"Cookie": f"demo_company={company_id}"}
    )

    assert response.status_code == 401
