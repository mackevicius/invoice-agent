from collections.abc import Callable
from contextlib import closing
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from invoice_agent.schemas.demo_company import DemoRole
from invoice_agent.schemas.invoice_fields import InvoiceFields
from invoice_agent.schemas.invoices import InvoiceDetail


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("Submitter", 403), ("Reviewer", 403), ("Admin", 200)],
)
def test_only_an_admin_can_change_the_auto_approval_limit(
    client: TestClient, role: DemoRole, expected_status: int
) -> None:
    client.post("/api/demo-company")
    initial = client.get("/api/demo-company/auto-approval-limit")
    assert initial.status_code == 200
    assert initial.json() == {"amount": "5000.00", "currency": "EUR"}

    response = client.put(
        "/api/demo-company/auto-approval-limit",
        headers={"X-Demo-Role": role},
        json={"amount": "2500.50"},
    )

    assert response.status_code == expected_status
    saved = client.get("/api/demo-company/auto-approval-limit")
    assert saved.json() == {
        "amount": "2500.50" if role == "Admin" else "5000.00",
        "currency": "EUR",
    }
    if role != "Admin":
        assert response.json()["detail"] == (
            "Only an Admin can change the Auto-Approval Limit."
        )


@pytest.mark.parametrize(
    ("action", "expected_status"), [("approve", "Approved"), ("reject", "Rejected")]
)
def test_reviewer_decisions_keep_the_limit_used_when_the_admin_changes_it(
    client: TestClient,
    upload_for_review: Callable[[DemoRole], InvoiceDetail],
    action: str,
    expected_status: str,
) -> None:
    invoice = upload_for_review("Submitter")
    changed = client.put(
        "/api/demo-company/auto-approval-limit",
        headers={"X-Demo-Role": "Admin"},
        json={"amount": "3000.00"},
    )
    assert changed.status_code == 200

    response = client.post(
        f"/api/invoices/{invoice.id}/{action}",
        headers={"X-Demo-Role": "Reviewer"},
        json={"rejection_reason": "Incorrect total."} if action == "reject" else None,
    )

    assert response.status_code == 200
    decided = response.json()
    assert decided["status"] == expected_status
    assert decided["auto_approval_limit"] == "3000.00"
    decided = client.get(
        f"/api/invoices/{invoice.id}", headers={"X-Demo-Role": "Reviewer"}
    ).json()
    changed = client.put(
        "/api/demo-company/auto-approval-limit",
        headers={"X-Demo-Role": "Admin"},
        json={"amount": "9000.00"},
    )
    assert changed.status_code == 200
    saved = client.get(
        f"/api/invoices/{invoice.id}", headers={"X-Demo-Role": "Reviewer"}
    )
    assert saved.json() == decided


def test_sample_decisions_keep_their_original_limit_after_an_admin_changes_it(
    client: TestClient,
) -> None:
    client.post("/api/demo-company")
    final_invoices = client.get("/api/invoices?view=done").json()
    assert {invoice["status"] for invoice in final_invoices} == {
        "Auto-Approved",
        "Approved",
        "Rejected",
    }
    decided = {
        invoice["id"]: client.get(f"/api/invoices/{invoice['id']}").json()
        for invoice in final_invoices
    }
    assert all(
        invoice["auto_approval_limit"] == "5000.00" for invoice in decided.values()
    )

    changed = client.put(
        "/api/demo-company/auto-approval-limit",
        headers={"X-Demo-Role": "Admin"},
        json={"amount": "0.00"},
    )

    assert changed.status_code == 200
    for invoice_id, invoice in decided.items():
        assert client.get(f"/api/invoices/{invoice_id}").json() == invoice


@pytest.mark.parametrize(
    ("amount", "expected_status", "expected_reasons"),
    [
        (
            "0.00",
            "In Review",
            ["Invoice total is at or above the Auto-Approval Limit of EUR 0.00."],
        ),
        ("9000.00", "Auto-Approved", []),
    ],
)
def test_a_new_limit_applies_to_future_decisions_not_an_auto_approved_invoice(
    client: TestClient,
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    amount: str,
    expected_status: str,
    expected_reasons: list[str],
) -> None:
    approved = process_invoice(matching_fields)
    decided = client.get(f"/api/invoices/{approved.id}").json()
    assert decided["status"] == "Auto-Approved"
    assert decided["auto_approval_limit"] == "5000.00"

    changed = client.put(
        "/api/demo-company/auto-approval-limit",
        headers={"X-Demo-Role": "Admin"},
        json={"amount": amount},
    )

    assert changed.status_code == 200
    assert client.get(f"/api/invoices/{approved.id}").json() == decided
    future = process_invoice(
        matching_fields.model_copy(
            update={"invoice_number": "INV-NEW-LIMIT", "total": Decimal("6000.00")}
        )
    )
    assert future.status == expected_status
    assert future.reasons == expected_reasons
    assert future.auto_approval_limit == Decimal(amount)


@pytest.mark.parametrize("amount", ["-0.01", "12.345", "1000000000000", "NaN"])
def test_invalid_limits_are_refused_without_changing_the_saved_limit(
    client: TestClient, amount: str
) -> None:
    client.post("/api/demo-company")

    response = client.put(
        "/api/demo-company/auto-approval-limit",
        headers={"X-Demo-Role": "Admin"},
        json={"amount": amount},
    )

    assert response.status_code == 422
    assert client.get("/api/demo-company/auto-approval-limit").json() == {
        "amount": "5000.00",
        "currency": "EUR",
    }


def test_limit_endpoints_require_a_demo_company(client: TestClient) -> None:
    assert client.get("/api/demo-company/auto-approval-limit").status_code == 401
    assert (
        client.put(
            "/api/demo-company/auto-approval-limit",
            headers={"X-Demo-Role": "Admin"},
            json={"amount": "1000.00"},
        ).status_code
        == 401
    )


def test_an_admin_changes_only_their_own_demo_company_limit(client: TestClient) -> None:
    client.post("/api/demo-company")
    assert (
        client.put(
            "/api/demo-company/auto-approval-limit",
            headers={"X-Demo-Role": "Admin"},
            json={"amount": "1234.56"},
        ).status_code
        == 200
    )

    with closing(TestClient(client.app)) as other_visitor:
        other_visitor.post("/api/demo-company")
        assert other_visitor.get("/api/demo-company/auto-approval-limit").json() == {
            "amount": "5000.00",
            "currency": "EUR",
        }
        assert (
            other_visitor.put(
                "/api/demo-company/auto-approval-limit",
                headers={"X-Demo-Role": "Admin"},
                json={"amount": "2345.67"},
            ).status_code
            == 200
        )

    assert client.get("/api/demo-company/auto-approval-limit").json() == {
        "amount": "1234.56",
        "currency": "EUR",
    }
