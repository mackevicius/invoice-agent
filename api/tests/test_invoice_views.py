from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from invoice_agent.schemas.demo_company import DemoRole
from invoice_agent.schemas.invoices import InvoiceDetail

REVIEW_SAMPLES = {
    ("INV-0309", "In Review"),
    ("INV-0217", "In Review"),
    ("INV-0781", "In Review"),
    ("INV-1046", "In Review"),
    ("INV-0001", "In Review"),
    ("INV-0782", "In Review"),
}
DONE_SAMPLES = {
    ("INV-1042", "Auto-Approved"),
    ("INV-0781", "Approved"),
    ("INV-1043", "Rejected"),
    ("INV-1044", "Auto-Approved"),
    ("INV-0218", "Auto-Approved"),
    ("INV-1045", "Auto-Approved"),
}


@pytest.mark.parametrize(
    ("view", "role", "expected_headers"),
    [
        (
            "all",
            "Admin",
            REVIEW_SAMPLES | DONE_SAMPLES | {(None, "In Review")},
        ),
        (
            "mine",
            "Submitter",
            REVIEW_SAMPLES | DONE_SAMPLES,
        ),
        ("mine", "Reviewer", {(None, "In Review")}),
        ("mine", "Admin", set()),
        ("review-queue", "Reviewer", REVIEW_SAMPLES | {(None, "In Review")}),
        ("done", "Reviewer", DONE_SAMPLES),
    ],
)
def test_invoice_views_filter_by_status_and_current_person(
    client: TestClient,
    upload_for_review: Callable[[DemoRole], InvoiceDetail],
    view: str,
    role: DemoRole,
    expected_headers: set[tuple[str | None, str]],
) -> None:
    upload_for_review("Reviewer")

    response = client.get(
        "/api/invoices", params={"view": view}, headers={"X-Demo-Role": role}
    )

    assert response.status_code == 200
    assert {
        (invoice["invoice_number"], invoice["status"]) for invoice in response.json()
    } == expected_headers
    assert len(response.json()) == len(expected_headers)


@pytest.mark.parametrize(
    ("role", "mine"), [("Submitter", 12), ("Reviewer", 1), ("Admin", 0)]
)
def test_counts_cover_every_view_and_update_after_a_decision(
    client: TestClient,
    upload_for_review: Callable[[DemoRole], InvoiceDetail],
    role: DemoRole,
    mine: int,
) -> None:
    upload_for_review("Reviewer")
    headers = {"X-Demo-Role": role}

    response = client.get("/api/invoices/counts", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"all": 13, "mine": mine, "review_queue": 7, "done": 6}
    invoice = next(
        invoice
        for invoice in client.get("/api/invoices?view=review-queue").json()
        if invoice["invoice_number"] == "INV-0309"
    )
    decided = client.post(
        f"/api/invoices/{invoice['id']}/approve",
        headers={"X-Demo-Role": "Reviewer"},
    )
    assert decided.status_code == 200
    assert client.get("/api/invoices/counts", headers=headers).json() == {
        "all": 13,
        "mine": mine,
        "review_queue": 6,
        "done": 7,
    }
