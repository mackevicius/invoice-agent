from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from invoice_agent.schemas.demo_company import DemoRole
from invoice_agent.schemas.invoices import InvoiceDetail


@pytest.mark.parametrize(
    ("view", "role", "expected_numbers"),
    [
        (
            "all",
            "Admin",
            {None, "INV-1042", "INV-0309", "INV-0781", "INV-1043", "INV-0217"},
        ),
        (
            "mine",
            "Submitter",
            {"INV-1042", "INV-0309", "INV-0781", "INV-1043", "INV-0217"},
        ),
        ("mine", "Reviewer", {None}),
        ("mine", "Admin", set()),
        ("review-queue", "Reviewer", {None, "INV-0309", "INV-0217"}),
        ("done", "Reviewer", {"INV-1042", "INV-0781", "INV-1043"}),
    ],
)
def test_invoice_views_filter_by_status_and_current_person(
    client: TestClient,
    upload_for_review: Callable[[DemoRole], InvoiceDetail],
    view: str,
    role: DemoRole,
    expected_numbers: set[str | None],
) -> None:
    upload_for_review("Reviewer")

    response = client.get(
        "/api/invoices", params={"view": view}, headers={"X-Demo-Role": role}
    )

    assert response.status_code == 200
    assert {
        invoice["invoice_number"] for invoice in response.json()
    } == expected_numbers
    assert len(response.json()) == len(expected_numbers)


@pytest.mark.parametrize(
    ("role", "mine"), [("Submitter", 5), ("Reviewer", 1), ("Admin", 0)]
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
    assert response.json() == {"all": 6, "mine": mine, "review_queue": 3, "done": 3}
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
        "all": 6,
        "mine": mine,
        "review_queue": 2,
        "done": 4,
    }
