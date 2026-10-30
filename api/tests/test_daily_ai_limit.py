from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Barrier, Thread
from typing import Literal
from uuid import UUID

import pytest
import time_machine
from fastapi.testclient import TestClient

from invoice_agent.clients.invoice_reader import ScriptedInvoiceReader
from invoice_agent.clients.line_pairing import ModelLinePairer
from invoice_agent.clients.vision_reader import VisionInvoiceReader
from invoice_agent.schemas.invoice_fields import InvoiceFields
from invoice_agent.schemas.invoices import InvoiceDetail, InvoiceFile
from invoice_agent.services.daily_ai_limit import DailyAILimit
from invoice_agent.services.erp_tools import ERPTools
from invoice_agent.services.invoices import InvoiceProcessing


@pytest.fixture
def document() -> InvoiceFile:
    return InvoiceFile(
        filename="invoice.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4\nInvoice",
    )


@pytest.fixture
def failing_model_api() -> Iterator[tuple[str, list[bytes]]]:
    requests: list[bytes] = []

    class FailingModelHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            requests.append(self.rfile.read(length))
            body = b'{"error":{"type":"api_error","message":"Unavailable"}}'
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("retry-after-ms", "1")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), FailingModelHandler) as server:
        server_thread = Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", requests
        finally:
            server.shutdown()
            server_thread.join()


class CountingInvoiceReader:
    uses_live_model = True

    def __init__(self) -> None:
        self.calls = 0

    def read(self, document: InvoiceFile) -> InvoiceFields | None:
        self.calls += 1
        return None


def test_visitor_daily_limit_blocks_the_model_and_records_review_reason(
    matching_company: UUID,
    database_url: str,
    erp_tools: ERPTools,
    document: InvoiceFile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INVOICE_AI_DAILY_VISITOR_LIMIT", "1")
    monkeypatch.setenv("INVOICE_AI_DAILY_GLOBAL_LIMIT", "10")
    reader = CountingInvoiceReader()
    processing = InvoiceProcessing(
        database_url,
        reader=reader,
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
    )
    first = processing.upload(matching_company, document)
    processing.process(matching_company, first.id)
    second = processing.upload(matching_company, document)
    resumed = InvoiceProcessing(
        database_url,
        reader=reader,
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
    )

    result = resumed.process(matching_company, second.id)

    assert reader.calls == 1
    assert result.status == "In Review"
    assert result.fields is None
    assert result.reasons == ["daily AI limit reached"]
    assert result.steps[0].status == "Failed"
    assert result.steps[0].outputs == {"reason": "daily AI limit reached"}
    assert all(step.status == "Skipped" for step in result.steps[1:])
    assert processing.get(matching_company, second.id) == result


@pytest.mark.parametrize(
    "visitor_limit,global_limit,expected_calls,expected_reason",
    [
        ("10", "1", 0, "daily AI limit reached"),
        ("1", "2", 1, "This file could not be read as an Invoice."),
    ],
)
def test_visitor_allowances_are_separate_but_the_global_limit_is_shared(
    client: TestClient,
    matching_company: UUID,
    database_url: str,
    erp_tools: ERPTools,
    document: InvoiceFile,
    monkeypatch: pytest.MonkeyPatch,
    visitor_limit: str,
    global_limit: str,
    expected_calls: int,
    expected_reason: str,
) -> None:
    monkeypatch.setenv("INVOICE_AI_DAILY_VISITOR_LIMIT", visitor_limit)
    monkeypatch.setenv("INVOICE_AI_DAILY_GLOBAL_LIMIT", global_limit)
    first_reader = CountingInvoiceReader()
    first_processing = InvoiceProcessing(
        database_url,
        reader=first_reader,
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
    )
    first = first_processing.upload(matching_company, document)
    first_processing.process(matching_company, first.id)
    with closing(TestClient(client.app)) as other_visitor:
        other_company = UUID(other_visitor.post("/api/demo-company").json()["id"])
    assert other_company != matching_company
    other_reader = CountingInvoiceReader()
    other_processing = InvoiceProcessing(
        database_url,
        reader=other_reader,
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
    )
    second = other_processing.upload(other_company, document)

    result = other_processing.process(other_company, second.id)

    assert first_reader.calls == 1
    assert other_reader.calls == expected_calls
    assert result.status == "In Review"
    assert result.reasons == [expected_reason]
    assert other_processing.get(other_company, second.id) == result


@pytest.mark.parametrize("visitor_limit,global_limit", [("1", "10"), ("10", "1")])
def test_daily_limits_reset_at_midnight_utc(
    client: TestClient,
    database_url: str,
    erp_tools: ERPTools,
    document: InvoiceFile,
    monkeypatch: pytest.MonkeyPatch,
    visitor_limit: str,
    global_limit: str,
) -> None:
    monkeypatch.setenv("INVOICE_AI_DAILY_VISITOR_LIMIT", visitor_limit)
    monkeypatch.setenv("INVOICE_AI_DAILY_GLOBAL_LIMIT", global_limit)
    reader = CountingInvoiceReader()
    processing = InvoiceProcessing(
        database_url,
        reader=reader,
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
    )
    with time_machine.travel(datetime(2026, 10, 28, 23, 59, tzinfo=UTC), tick=False):
        company_id = UUID(client.post("/api/demo-company").json()["id"])
        first = processing.upload(company_id, document)
        processing.process(company_id, first.id)
        second = processing.upload(company_id, document)
        blocked = processing.process(company_id, second.id)
        assert blocked.reasons == ["daily AI limit reached"]
        assert reader.calls == 1

    with time_machine.travel(datetime(2026, 10, 29, tzinfo=UTC), tick=False):
        third = processing.upload(company_id, document)

        result = processing.process(company_id, third.id)

        assert reader.calls == 2
        assert result.reasons == ["This file could not be read as an Invoice."]
        assert processing.get(company_id, third.id) == result


@pytest.mark.parametrize(
    "shared_visitor,visitor_limit,global_limit",
    [(True, "1", "10"), (False, "10", "1")],
)
def test_concurrent_workers_cannot_exceed_either_daily_limit(
    client: TestClient,
    matching_company: UUID,
    database_url: str,
    erp_tools: ERPTools,
    document: InvoiceFile,
    monkeypatch: pytest.MonkeyPatch,
    shared_visitor: bool,
    visitor_limit: str,
    global_limit: str,
) -> None:
    monkeypatch.setenv("INVOICE_AI_DAILY_VISITOR_LIMIT", visitor_limit)
    monkeypatch.setenv("INVOICE_AI_DAILY_GLOBAL_LIMIT", global_limit)
    company_ids = [matching_company] * 4
    if not shared_visitor:
        for index in range(1, 4):
            with closing(TestClient(client.app)) as other_visitor:
                company_ids[index] = UUID(
                    other_visitor.post("/api/demo-company").json()["id"]
                )
    readers = [CountingInvoiceReader() for _ in company_ids]
    processors = [
        InvoiceProcessing(
            database_url,
            reader=reader,
            erp_tools=erp_tools,
            daily_ai_limit=DailyAILimit(database_url),
        )
        for reader in readers
    ]
    invoice_ids = [
        processing.upload(company_id, document).id
        for processing, company_id in zip(processors, company_ids, strict=True)
    ]
    barrier = Barrier(len(processors))

    def process(index: int) -> InvoiceDetail:
        barrier.wait(timeout=10)
        return processors[index].process(company_ids[index], invoice_ids[index])

    with ThreadPoolExecutor(max_workers=len(processors)) as executor:
        results = list(executor.map(process, range(len(processors))))

    assert sum(reader.calls for reader in readers) == 1
    assert sum(result.reasons == ["daily AI limit reached"] for result in results) == 3
    assert all(result.status == "In Review" for result in results)
    for processing, company_id, result in zip(
        processors, company_ids, results, strict=True
    ):
        assert processing.get(company_id, result.id) == result


@pytest.mark.parametrize(
    "disabled_limit",
    ["INVOICE_AI_DAILY_VISITOR_LIMIT", "INVOICE_AI_DAILY_GLOBAL_LIMIT"],
)
def test_zero_daily_limit_disables_live_calls(
    matching_company: UUID,
    database_url: str,
    erp_tools: ERPTools,
    document: InvoiceFile,
    monkeypatch: pytest.MonkeyPatch,
    disabled_limit: str,
) -> None:
    monkeypatch.setenv("INVOICE_AI_DAILY_VISITOR_LIMIT", "10")
    monkeypatch.setenv("INVOICE_AI_DAILY_GLOBAL_LIMIT", "10")
    monkeypatch.setenv(disabled_limit, "0")
    reader = CountingInvoiceReader()
    processing = InvoiceProcessing(
        database_url,
        reader=reader,
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
    )
    uploaded = processing.upload(matching_company, document)

    result = processing.process(matching_company, uploaded.id)

    assert reader.calls == 0
    assert result.status == "In Review"
    assert result.reasons == ["daily AI limit reached"]
    assert processing.get(matching_company, uploaded.id) == result


def test_scripted_reads_do_not_use_or_require_the_live_daily_allowance(
    matching_company: UUID,
    database_url: str,
    erp_tools: ERPTools,
    document: InvoiceFile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INVOICE_AI_DAILY_VISITOR_LIMIT", "1")
    monkeypatch.setenv("INVOICE_AI_DAILY_GLOBAL_LIMIT", "1")
    scripted = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(None),
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
    )
    reader = CountingInvoiceReader()
    live = InvoiceProcessing(
        database_url,
        reader=reader,
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
    )
    fake_before = scripted.upload(matching_company, document)
    assert scripted.process(matching_company, fake_before.id).reasons == [
        "This file could not be read as an Invoice."
    ]
    first_live = live.upload(matching_company, document)
    assert live.process(matching_company, first_live.id).reasons == [
        "This file could not be read as an Invoice."
    ]
    over_limit = live.upload(matching_company, document)
    assert live.process(matching_company, over_limit.id).reasons == [
        "daily AI limit reached"
    ]
    fake_after = scripted.upload(matching_company, document)

    result = scripted.process(matching_company, fake_after.id)

    assert reader.calls == 1
    assert result.reasons == ["This file could not be read as an Invoice."]
    assert scripted.get(matching_company, fake_after.id) == result


def test_visitor_allowance_survives_demo_company_expiry_and_cleanup(
    client: TestClient,
    database_url: str,
    erp_tools: ERPTools,
    document: InvoiceFile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INVOICE_AI_DAILY_VISITOR_LIMIT", "1")
    monkeypatch.setenv("INVOICE_AI_DAILY_GLOBAL_LIMIT", "10")
    reader = CountingInvoiceReader()
    processing = InvoiceProcessing(
        database_url,
        reader=reader,
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
    )
    with time_machine.travel(datetime(2026, 10, 27, 12, tzinfo=UTC), tick=False):
        company_id = UUID(client.post("/api/demo-company").json()["id"])

    with time_machine.travel(datetime(2026, 10, 28, 11, tzinfo=UTC), tick=False):
        first = processing.upload(company_id, document)
        processing.process(company_id, first.id)
        assert reader.calls == 1

    with time_machine.travel(datetime(2026, 10, 28, 12, tzinfo=UTC), tick=False):
        with closing(TestClient(client.app)) as other_visitor:
            other_visitor.post("/api/demo-company")
        replacement_id = UUID(client.post("/api/demo-company").json()["id"])
        assert replacement_id != company_id
        assert processing.get(company_id, first.id) is None
        second = processing.upload(replacement_id, document)

        result = processing.process(replacement_id, second.id)

        assert reader.calls == 1
        assert result.status == "In Review"
        assert result.reasons == ["daily AI limit reached"]
        assert processing.get(replacement_id, second.id) == result


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_live_provider_does_not_retry_outside_the_daily_allowance(
    matching_company: UUID,
    database_url: str,
    erp_tools: ERPTools,
    document: InvoiceFile,
    failing_model_api: tuple[str, list[bytes]],
    monkeypatch: pytest.MonkeyPatch,
    provider: Literal["openai", "anthropic"],
) -> None:
    base_url, requests = failing_model_api
    monkeypatch.setenv("INVOICE_AI_DAILY_VISITOR_LIMIT", "1")
    monkeypatch.setenv("INVOICE_AI_DAILY_GLOBAL_LIMIT", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_API_BASE", base_url)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")
    monkeypatch.setenv("ANTHROPIC_API_URL", base_url)
    processing = InvoiceProcessing(
        database_url,
        reader=VisionInvoiceReader(provider=provider, model="test-model"),
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
    )
    first = processing.upload(matching_company, document)

    failed = processing.process(matching_company, first.id)

    assert len(requests) == 1
    assert failed.status == "In Review"
    assert failed.reasons == [
        "Invoice reading is unavailable. A Reviewer needs to check this Invoice."
    ]
    second = processing.upload(matching_company, document)
    blocked = processing.process(matching_company, second.id)
    assert blocked.reasons == ["daily AI limit reached"]
    assert len(requests) == 1


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_live_pairing_provider_does_not_retry_outside_the_daily_allowance(
    matching_company: UUID,
    matching_fields: InvoiceFields,
    database_url: str,
    erp_tools: ERPTools,
    document: InvoiceFile,
    failing_model_api: tuple[str, list[bytes]],
    monkeypatch: pytest.MonkeyPatch,
    provider: Literal["openai", "anthropic"],
) -> None:
    base_url, requests = failing_model_api
    monkeypatch.setenv("INVOICE_AI_DAILY_VISITOR_LIMIT", "1")
    monkeypatch.setenv("INVOICE_AI_DAILY_GLOBAL_LIMIT", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_API_BASE", base_url)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")
    monkeypatch.setenv("ANTHROPIC_API_URL", base_url)
    description = "A4 recycled paper in boxes"
    line = matching_fields.lines[0].model_copy(update={"description": description})
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(
            matching_fields.model_copy(update={"lines": [line]})
        ),
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
        line_pairer=ModelLinePairer(provider=provider, model="test-model"),
    )
    first = processing.upload(matching_company, document)

    failed = processing.process(matching_company, first.id)

    assert len(requests) == 1
    assert failed.status == "In Review"
    assert failed.comparison[0].purchase_order is None
    assert failed.reasons == [
        f"Line 1 ({description}): line pairing is unavailable. "
        "A Reviewer needs to check this line."
    ]
    second = processing.upload(matching_company, document)
    blocked = processing.process(matching_company, second.id)
    assert "daily AI limit reached" in blocked.reasons
    assert len(requests) == 1
    assert processing.get(matching_company, second.id) == blocked
