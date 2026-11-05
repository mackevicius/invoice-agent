from collections.abc import Callable
from datetime import date
from decimal import Decimal
from time import monotonic, sleep

import pytest
from fastapi.testclient import TestClient

from invoice_agent.app import create_app
from invoice_agent.clients.embeddings import ScriptedEmbeddings
from invoice_agent.clients.invoice_reader import ScriptedInvoiceReader
from invoice_agent.schemas.invoice_fields import InvoiceFields
from invoice_agent.schemas.invoices import InvoiceDetail


@pytest.fixture
def sample_client(
    database_url: str,
    embeddings: ScriptedEmbeddings,
    matching_fields: InvoiceFields,
) -> Callable[[str, str, str], TestClient]:
    def make_client(invoice_number: str, unit_price: str, total: str) -> TestClient:
        fields = matching_fields.model_copy(
            update={
                "invoice_number": invoice_number,
                "issued_on": date(2026, 11, 5),
                "lines": [
                    matching_fields.lines[0].model_copy(
                        update={"unit_price": Decimal(unit_price)}
                    )
                ],
                "subtotal": Decimal(total),
                "tax": Decimal("0.00"),
                "total": Decimal(total),
            }
        )
        return TestClient(
            create_app(
                database_url=database_url,
                cookie_secure=False,
                reader=ScriptedInvoiceReader(fields),
                embeddings=embeddings,
            )
        )

    return make_client


def upload_sample(client: TestClient, filename: str) -> InvoiceDetail:
    response = client.post(
        "/api/invoices",
        headers={"X-Demo-Role": "Submitter"},
        files={"file": (filename, b"%PDF-1.4\nInvoice", "application/pdf")},
    )
    assert response.status_code == 202
    uploaded = response.json()
    assert uploaded["filename"] == filename
    assert uploaded["status"] == "Processing"
    deadline = monotonic() + 5
    while monotonic() < deadline:
        result = InvoiceDetail.model_validate(
            client.get(f"/api/invoices/{uploaded['id']}").json()
        )
        if result.status != "Processing" and all(
            step.status not in {"Pending", "Running"} for step in result.steps
        ):
            return result
        sleep(0.01)
    pytest.fail("Sample Invoice processing did not finish.")


@pytest.mark.parametrize(
    "filename,invoice_number,unit_price,total,status,reasons",
    [
        pytest.param(
            "matching-invoice.pdf",
            "DEMO-MATCH-001",
            "111.60",
            "2678.40",
            "Auto-Approved",
            [],
            id="matching",
        ),
        pytest.param(
            "overcharged-invoice.pdf",
            "DEMO-OVER-001",
            "120.00",
            "2880.00",
            "In Review",
            [
                "Line 1 (Recycled A4 paper, box): unit price is more than 2% "
                "above the Purchase Order."
            ],
            id="overcharged",
        ),
    ],
)
def test_sample_fields_are_decided_against_the_seeded_demo_company(
    sample_client: Callable[[str, str, str], TestClient],
    filename: str,
    invoice_number: str,
    unit_price: str,
    total: str,
    status: str,
    reasons: list[str],
) -> None:
    with sample_client(invoice_number, unit_price, total) as client:
        client.post("/api/demo-company").raise_for_status()

        result = upload_sample(client, filename)

    assert result.invoice_number == invoice_number
    assert result.total == Decimal(total)
    assert result.status == status
    assert result.reasons == reasons
    assert all(step.status == "Completed" for step in result.steps)


def test_repeating_the_matching_sample_needs_review_as_a_duplicate(
    sample_client: Callable[[str, str, str], TestClient],
) -> None:
    with sample_client("DEMO-MATCH-001", "111.60", "2678.40") as client:
        client.post("/api/demo-company").raise_for_status()
        first = upload_sample(client, "matching-invoice.pdf")

        repeated = upload_sample(client, "matching-invoice.pdf")

    assert first.status == "Auto-Approved"
    assert repeated.id != first.id
    assert repeated.status == "In Review"
    assert repeated.reasons == [
        "Duplicate Invoice: DEMO-MATCH-001 was already received."
    ]
