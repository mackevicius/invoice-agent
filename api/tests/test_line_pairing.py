from collections.abc import Callable
from contextlib import closing
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from invoice_agent.app import create_app
from invoice_agent.clients.embeddings import ScriptedEmbeddings
from invoice_agent.clients.invoice_reader import ScriptedInvoiceReader
from invoice_agent.clients.line_pairing import ScriptedLinePairer
from invoice_agent.schemas.invoice_fields import InvoiceFields, InvoiceLine
from invoice_agent.schemas.invoices import InvoiceDetail, InvoiceFile
from invoice_agent.services.daily_ai_limit import DailyAILimit
from invoice_agent.services.erp_tools import ERPTools
from invoice_agent.services.invoices import InvoiceProcessing


def test_differently_worded_lines_are_paired_by_meaning(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    pairing_choices: dict[str, str | UUID | Exception | None],
) -> None:
    description = "A4 recycled paper in boxes"
    pairing_choices[description] = "Recycled A4 paper, box"
    line = matching_fields.lines[0].model_copy(update={"description": description})

    result = process_invoice(matching_fields.model_copy(update={"lines": [line]}))

    comparison = result.comparison[0]
    assert comparison.purchase_order is not None
    assert comparison.purchase_order.description == "Recycled A4 paper, box"
    assert comparison.invoice.description == description
    assert comparison.paired_by == "meaning"
    assert result.status == "Auto-Approved"
    assert result.reasons == []


def test_unavailable_model_leaves_the_line_unpaired_with_a_clear_reason(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    pairing_choices: dict[str, str | UUID | Exception | None],
) -> None:
    description = "A4 recycled paper in boxes"
    pairing_choices[description] = RuntimeError("The model is unavailable.")
    line = matching_fields.lines[0].model_copy(update={"description": description})

    result = process_invoice(matching_fields.model_copy(update={"lines": [line]}))

    assert result.status == "In Review"
    assert result.comparison[0].purchase_order is None
    assert result.reasons == [
        f"Line 1 ({description}): line pairing is unavailable. "
        "A Reviewer needs to check this line."
    ]
    assert next(step for step in result.steps if step.name == "Pair Lines").status == (
        "Failed"
    )


def test_model_chooses_from_ranked_candidates_not_just_the_nearest(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    matching_company: UUID,
    database_url: str,
    pairing_choices: dict[str, str | UUID | Exception | None],
) -> None:
    description = "10mm hex bolt zinc"
    purchase_description = "Bolt, hex, M10, galvanised"
    pairing_choices[description] = purchase_description
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """UPDATE purchase_order_lines SET description = %s, embedding = %s::vector
               WHERE company_id = %s AND description = 'Recycled A4 paper, box'""",
            (purchase_description, [0.8, 0.6] + [0.0] * 382, matching_company),
        )
        for position in range(6):
            candidate_description = (
                "A nearby but different bolt"
                if position == 0
                else f"Unrelated item {position}"
            )
            vector = [1.0] + [0.0] * 383 if position == 0 else [0.0, 1.0] + [0.0] * 382
            connection.execute(
                """INSERT INTO purchase_order_lines
                   (id, company_id, purchase_order_id, description,
                    quantity, unit_price, embedding, embedding_model)
                   SELECT %s, company_id, id, %s, 24, 111.60, %s::vector, 'scripted'
                   FROM purchase_orders WHERE company_id = %s AND number = 'PO-1002'""",
                (uuid4(), candidate_description, vector, matching_company),
            )
    line = matching_fields.lines[0].model_copy(update={"description": description})

    result = process_invoice(matching_fields.model_copy(update={"lines": [line]}))

    assert result.comparison[0].purchase_order is not None
    assert result.comparison[0].purchase_order.description == purchase_description
    assert result.status == "Auto-Approved"
    assert result.reasons == []
    step = next(step for step in result.steps if step.name == "Pair Lines")
    assert step.outputs is not None
    searches = step.outputs["candidate_searches"]
    assert isinstance(searches, list)
    search = searches[0]
    assert isinstance(search, dict)
    candidates = search["candidates"]
    assert isinstance(candidates, list)
    descriptions = [
        candidate["description"]
        for candidate in candidates
        if isinstance(candidate, dict)
    ]
    assert len(descriptions) == 5
    assert descriptions[:2] == ["A nearby but different bolt", purchase_description]


def test_existing_lines_are_reembedded_when_the_embedding_model_changes(
    matching_company: UUID,
    matching_fields: InvoiceFields,
    database_url: str,
) -> None:
    class ChangedEmbeddings(ScriptedEmbeddings):
        @property
        def model_name(self) -> str:
            return "changed-scripted-model"

    description = "A4 recycled paper in boxes"
    with psycopg.connect(database_url) as connection:
        for position in range(5):
            connection.execute(
                """INSERT INTO purchase_order_lines
                   (id, company_id, purchase_order_id, description,
                    quantity, unit_price, embedding, embedding_model)
                   SELECT %s, company_id, id, %s, 24, 111.60, %s::vector, 'scripted'
                   FROM purchase_orders WHERE company_id = %s AND number = 'PO-1002'""",
                (
                    uuid4(),
                    f"Unrelated old-model item {position}",
                    [0.0, 1.0] + [0.0] * 382,
                    matching_company,
                ),
            )
    embeddings = ChangedEmbeddings(
        {
            description: [0.0, 1.0] + [0.0] * 382,
            "Recycled A4 paper, box": [0.0, 1.0] + [0.0] * 382,
        }
    )
    with TestClient(
        create_app(
            database_url=database_url,
            cookie_secure=False,
            reader=ScriptedInvoiceReader(None),
            embeddings=embeddings,
        )
    ):
        pass
    line = matching_fields.lines[0].model_copy(update={"description": description})
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(
            matching_fields.model_copy(update={"lines": [line]})
        ),
        erp_tools=ERPTools(database_url, embeddings),
        daily_ai_limit=DailyAILimit(database_url),
        line_pairer=ScriptedLinePairer({description: "Recycled A4 paper, box"}),
    )
    uploaded = processing.upload(
        matching_company,
        InvoiceFile(
            filename="invoice.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4\nInvoice",
        ),
    )

    result = processing.process(matching_company, uploaded.id)

    assert result.comparison[0].purchase_order is not None
    assert result.comparison[0].purchase_order.description == "Recycled A4 paper, box"
    assert result.status == "Auto-Approved"
    assert result.reasons == []
    assert processing.get(matching_company, uploaded.id) == result


@pytest.mark.parametrize("choice", [None, UUID(int=1)])
def test_refused_or_out_of_candidate_choices_leave_the_line_unpaired(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    pairing_choices: dict[str, str | UUID | Exception | None],
    choice: UUID | None,
) -> None:
    description = "An item that does not fit the candidates"
    pairing_choices[description] = choice
    line = matching_fields.lines[0].model_copy(update={"description": description})

    result = process_invoice(matching_fields.model_copy(update={"lines": [line]}))

    assert result.status == "In Review"
    assert result.comparison[0].purchase_order is None
    assert result.comparison[0].price_passed is False
    assert result.comparison[0].quantity_passed is False
    assert result.reasons == [f"Line 1 ({description}): no paired Purchase Order line."]


@pytest.mark.parametrize(
    "second_description", ["Recycled A4 paper, box", "More boxes of recycled A4 paper"]
)
def test_semantic_pairing_cannot_reuse_a_line_or_take_an_exact_match(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    pairing_choices: dict[str, str | UUID | Exception | None],
    second_description: str,
) -> None:
    first_description = "A4 recycled paper in boxes"
    purchase_description = "Recycled A4 paper, box"
    pairing_choices[first_description] = purchase_description
    pairing_choices[second_description] = purchase_description
    lines = [
        matching_fields.lines[0].model_copy(update={"description": description})
        for description in [first_description, second_description]
    ]

    result = process_invoice(matching_fields.model_copy(update={"lines": lines}))

    paired_index = 1 if second_description == purchase_description else 0
    assert result.comparison[paired_index].purchase_order is not None
    assert result.comparison[1 - paired_index].purchase_order is None
    assert result.status == "In Review"


def test_semantic_candidates_stay_inside_the_named_purchase_order_and_company(
    client: TestClient,
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    pairing_choices: dict[str, str | UUID | Exception | None],
) -> None:
    with closing(TestClient(client.app)) as other_visitor:
        assert other_visitor.post("/api/demo-company").status_code == 200
    description = "A4 recycled paper in boxes"
    pairing_choices[description] = "Recycled A4 paper, box"
    line = matching_fields.lines[0].model_copy(update={"description": description})

    result = process_invoice(matching_fields.model_copy(update={"lines": [line]}))

    assert result.comparison[0].purchase_order is not None
    step = next(step for step in result.steps if step.name == "Pair Lines")
    assert step.outputs is not None
    searches = step.outputs["candidate_searches"]
    assert isinstance(searches, list)
    search = searches[0]
    assert isinstance(search, dict)
    candidates = search["candidates"]
    assert isinstance(candidates, list)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert isinstance(candidate, dict)
    assert candidate["description"] == "Recycled A4 paper, box"
    assert result.status == "Auto-Approved"
    assert result.reasons == []


def test_semantic_choices_do_not_override_conflicting_item_codes(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    matching_company: UUID,
    database_url: str,
    pairing_choices: dict[str, str | UUID | Exception | None],
) -> None:
    description = "A4 recycled paper in boxes"
    pairing_choices[description] = "Recycled A4 paper, box"
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """UPDATE purchase_order_lines SET item_code = 'PAPER-A4'
               WHERE company_id = %s""",
            (matching_company,),
        )
    line = matching_fields.lines[0].model_copy(
        update={"description": description, "item_code": "OTHER-ITEM"}
    )

    result = process_invoice(matching_fields.model_copy(update={"lines": [line]}))

    assert result.comparison[0].purchase_order is None
    assert result.reasons == [f"Line 1 ({description}): no paired Purchase Order line."]


def test_daily_limit_prevents_a_live_line_pairing_choice(
    matching_company: UUID,
    matching_fields: InvoiceFields,
    database_url: str,
    erp_tools: ERPTools,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class LiveScriptedLinePairer(ScriptedLinePairer):
        @property
        def uses_live_model(self) -> bool:
            return True

    monkeypatch.setenv("INVOICE_AI_DAILY_VISITOR_LIMIT", "0")
    description = "A4 recycled paper in boxes"
    line = matching_fields.lines[0].model_copy(update={"description": description})
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(
            matching_fields.model_copy(update={"lines": [line]})
        ),
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
        line_pairer=LiveScriptedLinePairer({description: "Recycled A4 paper, box"}),
    )
    uploaded = processing.upload(
        matching_company,
        InvoiceFile(
            filename="invoice.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4\nInvoice",
        ),
    )

    result = processing.process(matching_company, uploaded.id)

    assert result.status == "In Review"
    assert "daily AI limit reached" in result.reasons
    assert result.comparison[0].purchase_order is None
    assert next(step for step in result.steps if step.name == "Pair Lines").status == (
        "Failed"
    )
    assert processing.get(matching_company, uploaded.id) == result


@pytest.mark.parametrize(
    ("item_code", "description", "paired_by"),
    [
        ("PAPER-A4", "Paper supplied in boxes", "item_code"),
        (None, "Recycled A4 paper, box", "description"),
        ("OTHER-ITEM", "Recycled A4 paper, box", None),
        (None, "Extra packing charge", None),
        (None, "Recycled A4 paper", None),
    ],
)
def test_only_clearly_corresponding_lines_are_paired(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    matching_company: UUID,
    database_url: str,
    item_code: str | None,
    description: str,
    paired_by: str | None,
) -> None:
    original = matching_fields.lines[0]
    line = InvoiceLine(
        item_code=item_code,
        description=description,
        quantity=original.quantity,
        unit_price=original.unit_price,
    )
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """UPDATE purchase_order_lines SET item_code = 'PAPER-A4'
               WHERE company_id = %s""",
            (matching_company,),
        )

    result = process_invoice(matching_fields.model_copy(update={"lines": [line]}))

    assert result.status == ("In Review" if paired_by is None else "Auto-Approved")
    comparison = result.comparison[0]
    assert comparison.paired_by == paired_by
    if paired_by is None:
        assert comparison.purchase_order is None
        assert comparison.price_passed is False
        assert comparison.quantity_passed is False
        assert result.reasons == [
            f"Line 1 ({description}): no paired Purchase Order line."
        ]
    else:
        assert comparison.purchase_order is not None
        assert comparison.purchase_order.item_code == "PAPER-A4"
        assert result.reasons == []


def test_every_failure_is_reported_across_invoice_lines(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
) -> None:
    overcharged = matching_fields.lines[0].model_copy(
        update={"quantity": Decimal("30"), "unit_price": Decimal("120.00")}
    )
    unpaired = InvoiceLine(
        description="Extra packing charge",
        quantity=Decimal("1"),
        unit_price=Decimal("3.00"),
    )

    result = process_invoice(
        matching_fields.model_copy(update={"lines": [overcharged, unpaired]})
    )

    assert result.status == "In Review"
    assert result.reasons == [
        "Line 1 (Recycled A4 paper, box): unit price is more than 2% "
        "above the Purchase Order.",
        "Line 1 (Recycled A4 paper, box): invoiced quantity does not equal "
        "received quantity.",
        "Line 2 (Extra packing charge): no paired Purchase Order line.",
    ]
    assert len(result.comparison) == 2
    assert result.comparison[1].purchase_order is None
    assert result.comparison[1].goods_receipt is None


def test_identical_description_resolves_a_repeated_item_code(
    process_invoice: Callable[[InvoiceFields], InvoiceDetail],
    matching_fields: InvoiceFields,
    matching_company: UUID,
    database_url: str,
) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """UPDATE purchase_order_lines SET item_code = 'SERVICE'
               WHERE company_id = %s""",
            (matching_company,),
        )
        connection.execute(
            """INSERT INTO purchase_order_lines
               (id, company_id, purchase_order_id, item_code,
                description, quantity, unit_price)
               SELECT %s, company_id, id, 'SERVICE', 'Additional paper boxes',
                      24, 111.60
               FROM purchase_orders WHERE company_id = %s AND number = 'PO-1002'""",
            (uuid4(), matching_company),
        )
    line = matching_fields.lines[0].model_copy(update={"item_code": "SERVICE"})

    result = process_invoice(matching_fields.model_copy(update={"lines": [line]}))

    assert result.status == "Auto-Approved"
    assert result.reasons == []
    assert result.comparison[0].paired_by == "description"
    assert result.comparison[0].purchase_order is not None
    assert result.comparison[0].purchase_order.description == "Recycled A4 paper, box"
