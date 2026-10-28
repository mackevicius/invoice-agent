from collections.abc import Callable
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from invoice_agent.schemas.demo_company import DemoRole
from invoice_agent.schemas.invoices import InvoiceDetail


@pytest.mark.parametrize("role", ["Submitter", "Admin"])
@pytest.mark.parametrize("action", ["approve", "reject"])
def test_only_a_reviewer_can_decide_an_invoice(
    client: TestClient, role: DemoRole, action: str
) -> None:
    client.post("/api/demo-company")
    invoice = next(
        invoice
        for invoice in client.get("/api/invoices").json()
        if invoice["status"] == "In Review"
    )

    response = client.post(
        f"/api/invoices/{invoice['id']}/{action}",
        headers={"X-Demo-Role": role},
        json={"rejection_reason": "The goods did not arrive."},
    )

    assert response.status_code == 403


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_a_reviewer_cannot_decide_their_own_upload(
    client: TestClient,
    upload_for_review: Callable[[DemoRole], InvoiceDetail],
    action: str,
) -> None:
    invoice = upload_for_review("Reviewer")

    response = client.post(
        f"/api/invoices/{invoice.id}/{action}",
        headers={"X-Demo-Role": "Reviewer"},
        json={"rejection_reason": "The goods did not arrive."},
    )

    assert response.status_code == 403
    assert client.get(f"/api/invoices/{invoice.id}").json()["status"] == "In Review"


@pytest.mark.parametrize(
    ("uploaded_as", "viewing_as", "can_decide", "block_reason"),
    [
        ("Submitter", "Reviewer", True, None),
        ("Admin", "Reviewer", True, None),
        (
            "Reviewer",
            "Reviewer",
            False,
            "You cannot decide an Invoice you uploaded.",
        ),
        ("Submitter", "Submitter", False, "Only a Reviewer can decide an Invoice."),
        ("Submitter", "Admin", False, "Only a Reviewer can decide an Invoice."),
    ],
)
def test_invoice_detail_reports_decision_access_for_the_current_person(
    client: TestClient,
    upload_for_review: Callable[[DemoRole], InvoiceDetail],
    uploaded_as: DemoRole,
    viewing_as: DemoRole,
    can_decide: bool,
    block_reason: str | None,
) -> None:
    invoice = upload_for_review(uploaded_as)

    response = client.get(
        f"/api/invoices/{invoice.id}", headers={"X-Demo-Role": viewing_as}
    )

    assert response.status_code == 200
    assert response.json()["submitted_by"] == uploaded_as.lower()
    assert response.json()["can_decide"] is can_decide
    assert response.json()["decision_block_reason"] == block_reason


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_a_decision_requires_the_invoices_demo_company(
    client: TestClient, action: str
) -> None:
    client.post("/api/demo-company")
    invoice_id = client.get("/api/invoices?view=review-queue").json()[0]["id"]
    with closing(TestClient(client.app)) as stranger:
        unauthenticated = stranger.post(
            f"/api/invoices/{invoice_id}/{action}",
            headers={"X-Demo-Role": "Reviewer"},
            json={"rejection_reason": "The goods did not arrive."},
        )
        assert unauthenticated.status_code == 401
        stranger.post("/api/demo-company")

        response = stranger.post(
            f"/api/invoices/{invoice_id}/{action}",
            headers={"X-Demo-Role": "Reviewer"},
            json={"rejection_reason": "The goods did not arrive."},
        )

    assert response.status_code == 404
    assert client.get(f"/api/invoices/{invoice_id}").json()["status"] == "In Review"
