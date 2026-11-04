from contextlib import closing
from datetime import UTC, datetime
from uuid import UUID

import pytest
import time_machine
from fastapi.testclient import TestClient

from invoice_agent.services.erp_tools import ERPTools


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


@pytest.mark.parametrize("role", ["Submitter", "Reviewer", "Admin"])
def test_invoice_downloads_are_scoped_to_the_visitors_demo_company(
    client: TestClient,
    role: str,
) -> None:
    client.post("/api/demo-company")
    content = b"%PDF-1.4\nPrivate Invoice"
    uploaded = client.post(
        "/api/invoices",
        files={"file": ("invoice.pdf", content, "application/pdf")},
    )
    assert uploaded.status_code == 202
    path = f"/api/invoices/{uploaded.json()['id']}/file"

    download = client.get(path, headers={"X-Demo-Role": role})

    assert download.status_code == 200
    assert download.content == content
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"].startswith("attachment;")
    assert "no-store" in download.headers["cache-control"]

    with closing(TestClient(client.app)) as other_visitor:
        assert other_visitor.get(path).status_code == 401
        other_visitor.post("/api/demo-company")
        assert other_visitor.get(path, headers={"X-Demo-Role": role}).status_code == 404


@pytest.mark.parametrize("decision", ["approve", "reject"])
@pytest.mark.parametrize("role", ["Submitter", "Reviewer", "Admin"])
def test_visitors_cannot_decide_another_companys_invoice(
    client: TestClient,
    decision: str,
    role: str,
) -> None:
    client.post("/api/demo-company")
    invoice = next(
        invoice
        for invoice in client.get("/api/invoices").json()
        if invoice["status"] == "In Review"
    )
    path = f"/api/invoices/{invoice['id']}"

    with closing(TestClient(client.app)) as other_visitor:
        other_visitor.post("/api/demo-company")
        response = other_visitor.post(
            f"{path}/{decision}",
            headers={"X-Demo-Role": role},
            json={"rejection_reason": "Not our Invoice."},
        )

        assert response.status_code == 404

    assert client.get(path).json()["status"] == "In Review"


def test_erp_tools_refuse_records_from_another_demo_company(
    client: TestClient,
    erp_tools: ERPTools,
) -> None:
    company_id = UUID(client.post("/api/demo-company").json()["id"])
    invoice_id = UUID(client.get("/api/invoices").json()[0]["id"])
    supplier = erp_tools.find_supplier(company_id, "Paper & Co.")
    assert supplier is not None

    with closing(TestClient(client.app)) as other_visitor:
        other_company_id = UUID(other_visitor.post("/api/demo-company").json()["id"])
        other_invoice_id = UUID(other_visitor.get("/api/invoices").json()[0]["id"])

    other_supplier = erp_tools.find_supplier(other_company_id, "Paper & Co.")
    assert other_supplier is not None
    assert supplier.id != other_supplier.id
    other_purchase_order = erp_tools.get_purchase_order(
        other_company_id, other_supplier.id, "PO-1002"
    )
    assert other_purchase_order is not None

    assert (
        erp_tools.get_purchase_order(company_id, other_supplier.id, "PO-1002") is None
    )
    assert erp_tools.get_goods_receipt(company_id, other_purchase_order.id) is None
    assert (
        erp_tools.search_purchase_order_lines(
            company_id, other_purchase_order.id, "Recycled A4 paper, box"
        )
        == []
    )
    assert (
        erp_tools.find_earlier_invoices(company_id, other_supplier.id, invoice_id) == []
    )
    assert (
        erp_tools.find_earlier_invoices(company_id, supplier.id, other_invoice_id) == []
    )


def test_erp_tools_refuse_expired_demo_company_data(
    client: TestClient,
    erp_tools: ERPTools,
) -> None:
    with time_machine.travel(datetime(2026, 10, 26, 12, tzinfo=UTC), tick=False):
        company_id = UUID(client.post("/api/demo-company").json()["id"])
        invoice_id = UUID(client.get("/api/invoices").json()[0]["id"])
        supplier = erp_tools.find_supplier(company_id, "Paper & Co.")
        assert supplier is not None
        purchase_order = erp_tools.get_purchase_order(
            company_id, supplier.id, "PO-1002"
        )
        assert purchase_order is not None
        assert erp_tools.get_goods_receipt(company_id, purchase_order.id) is not None
        assert erp_tools.search_purchase_order_lines(
            company_id, purchase_order.id, "Recycled A4 paper, box"
        )

    with time_machine.travel(datetime(2026, 10, 27, 12, tzinfo=UTC), tick=False):
        assert erp_tools.find_supplier(company_id, "Paper & Co.") is None
        assert erp_tools.get_purchase_order(company_id, supplier.id, "PO-1002") is None
        assert erp_tools.get_goods_receipt(company_id, purchase_order.id) is None
        assert (
            erp_tools.search_purchase_order_lines(
                company_id, purchase_order.id, "Recycled A4 paper, box"
            )
            == []
        )
        assert (
            erp_tools.find_earlier_invoices(company_id, supplier.id, invoice_id) == []
        )
