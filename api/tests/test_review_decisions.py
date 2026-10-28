from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from invoice_agent.schemas.demo_company import DemoRole
from invoice_agent.schemas.invoices import InvoiceDetail


@pytest.mark.parametrize("reason", [None, "", "   ", "\n\t"])
def test_rejecting_requires_a_rejection_reason(
    client: TestClient, reason: str | None
) -> None:
    client.post("/api/demo-company")
    invoice = next(
        invoice
        for invoice in client.get("/api/invoices").json()
        if invoice["status"] == "In Review"
    )

    response = client.post(
        f"/api/invoices/{invoice['id']}/reject",
        headers={"X-Demo-Role": "Reviewer"},
        json={"rejection_reason": reason} if reason is not None else {},
    )

    assert response.status_code == 422
    assert client.get(f"/api/invoices/{invoice['id']}").json()["status"] == "In Review"


@pytest.mark.parametrize(
    ("action", "status", "reason"),
    [("approve", "Approved", None), ("reject", "Rejected", "The price is incorrect.")],
)
def test_decisions_are_final_and_rejection_reasons_are_visible_to_submitters(
    client: TestClient,
    upload_for_review: Callable[[DemoRole], InvoiceDetail],
    action: str,
    status: str,
    reason: str | None,
) -> None:
    invoice = upload_for_review("Submitter")
    headers = {"X-Demo-Role": "Reviewer"}

    response = client.post(
        f"/api/invoices/{invoice.id}/{action}",
        headers=headers,
        json={"rejection_reason": f"  {reason}  "} if reason else None,
    )

    assert response.status_code == 200
    assert response.json()["status"] == status
    assert response.json()["can_decide"] is False
    persisted = client.get(
        f"/api/invoices/{invoice.id}", headers={"X-Demo-Role": "Submitter"}
    ).json()
    assert persisted["status"] == status
    assert persisted["rejection_reason"] == reason
    assert persisted["reasons"] == invoice.reasons
    for next_action in ("approve", "reject"):
        repeated = client.post(
            f"/api/invoices/{invoice.id}/{next_action}",
            headers=headers,
            json={"rejection_reason": "A different decision."},
        )
        assert repeated.status_code == 409
    unchanged = client.get(f"/api/invoices/{invoice.id}").json()
    assert unchanged["status"] == status
    assert unchanged["rejection_reason"] == reason


def test_an_auto_approved_invoice_cannot_be_decided_again(client: TestClient) -> None:
    client.post("/api/demo-company")
    invoice = next(
        invoice
        for invoice in client.get("/api/invoices?view=done").json()
        if invoice["status"] == "Auto-Approved"
    )

    response = client.post(
        f"/api/invoices/{invoice['id']}/approve",
        headers={"X-Demo-Role": "Reviewer"},
    )

    assert response.status_code == 409
    assert (
        client.get(f"/api/invoices/{invoice['id']}").json()["status"] == "Auto-Approved"
    )
