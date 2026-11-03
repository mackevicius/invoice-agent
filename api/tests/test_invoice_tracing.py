import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
from uuid import UUID, uuid4

import httpx
import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from invoice_agent.clients.invoice_reader import ScriptedInvoiceReader
from invoice_agent.clients.line_pairing import ModelLinePairer
from invoice_agent.clients.tracing import RunTracing, configured_tracing
from invoice_agent.clients.vision_reader import VisionInvoiceReader
from invoice_agent.schemas.invoice_fields import InvoiceFields
from invoice_agent.schemas.invoices import InvoiceFile
from invoice_agent.services.daily_ai_limit import DailyAILimit
from invoice_agent.services.erp_tools import ERPTools
from invoice_agent.services.invoice_processing import InvoiceProcessing


@pytest.fixture
def project_status() -> int:
    return 200


@pytest.fixture
def trace_capture(
    project_status: int,
) -> Iterator[tuple[Langfuse, InMemorySpanExporter, str]]:
    public_key = f"pk-lf-test-{uuid4()}"
    exporter = InMemorySpanExporter()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            project_status,
            json={
                "data": [
                    {
                        "id": "trace-project",
                        "name": "Trace tests",
                        "organization": {"id": "test-org", "name": "Tests"},
                        "metadata": {},
                    }
                ]
            },
        )
    )
    with httpx.Client(transport=transport) as http_client:
        tracing = Langfuse(
            public_key=public_key,
            secret_key="sk-lf-test",
            base_url="https://langfuse.test",
            httpx_client=http_client,
            tracer_provider=TracerProvider(),
            span_exporter=exporter,
        )
        try:
            yield tracing, exporter, public_key
        finally:
            tracing.shutdown()


def test_configured_run_saves_one_trace_with_every_step(
    matching_company: UUID,
    matching_fields: InvoiceFields,
    database_url: str,
    erp_tools: ERPTools,
    trace_capture: tuple[Langfuse, InMemorySpanExporter, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracing, exporter, public_key = trace_capture
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", public_key)
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://langfuse.test")
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(matching_fields),
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
        tracing=configured_tracing(),
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
    tracing.flush()

    assert result.trace_url is not None
    assert result.trace_url.startswith(
        "https://langfuse.test/project/trace-project/traces/"
    )
    saved = processing.get(matching_company, uploaded.id)
    assert saved is not None
    assert saved.trace_url == result.trace_url
    spans = exporter.get_finished_spans()
    trace_id = int(result.trace_url.rsplit("/", 1)[-1], 16)
    assert {span.context.trace_id for span in spans if span.context} == {trace_id}
    span_ids = {span.context.span_id for span in spans if span.context}
    assert [
        span.name
        for span in spans
        if span.parent is None or span.parent.span_id not in span_ids
    ] == ["Invoice run"]
    assert {
        "read_invoice",
        "find_supplier",
        "find_purchase_order",
        "find_goods_receipt",
        "pair_lines",
        "three_way_match",
        "check_duplicates",
        "decide",
    } <= {span.name for span in spans}
    assert {
        "find_supplier",
        "get_purchase_order",
        "get_goods_receipt",
        "find_earlier_invoices",
    } <= {
        span.name
        for span in spans
        if span.attributes
        and span.attributes.get("langfuse.observation.type") == "tool"
    }
    assert all(
        span.start_time is not None
        and span.end_time is not None
        and span.end_time >= span.start_time
        for span in spans
    )


def test_concurrent_runs_keep_separate_traces(
    matching_company: UUID,
    matching_fields: InvoiceFields,
    database_url: str,
    erp_tools: ERPTools,
    trace_capture: tuple[Langfuse, InMemorySpanExporter, str],
) -> None:
    tracing, exporter, public_key = trace_capture
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(matching_fields),
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
        tracing=RunTracing(tracing, public_key=public_key),
    )
    uploads = [
        processing.upload(
            matching_company,
            InvoiceFile(
                filename="invoice.pdf",
                content_type="application/pdf",
                content=b"%PDF-1.4\nInvoice",
            ),
        )
        for _ in range(2)
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda invoice: processing.process(matching_company, invoice.id),
                uploads,
            )
        )
    tracing.flush()

    assert all(result.trace_url is not None for result in results)
    assert results[0].trace_url != results[1].trace_url
    expected = {
        str(result.id): int(result.trace_url.rsplit("/", 1)[-1], 16)
        for result in results
        if result.trace_url is not None
    }
    actual: dict[str, int] = {}
    for span in exporter.get_finished_spans():
        if span.name != "Invoice run":
            continue
        assert span.attributes is not None
        assert span.context is not None
        inputs = span.attributes["langfuse.observation.input"]
        assert isinstance(inputs, str)
        actual[json.loads(inputs)["invoice_id"]] = span.context.trace_id
    assert actual == expected


def test_failed_reading_still_has_a_trace_and_records_skipped_steps(
    matching_company: UUID,
    database_url: str,
    erp_tools: ERPTools,
    trace_capture: tuple[Langfuse, InMemorySpanExporter, str],
) -> None:
    tracing, exporter, public_key = trace_capture
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(None),
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
        tracing=RunTracing(tracing, public_key=public_key),
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
    tracing.flush()

    assert result.status == "In Review"
    assert result.trace_url is not None
    assert result.steps[0].status == "Failed"
    assert all(step.status == "Skipped" for step in result.steps[1:])
    spans = exporter.get_finished_spans()
    root = next(span for span in spans if span.name == "Invoice run")
    assert root.attributes is not None
    output = root.attributes["langfuse.observation.output"]
    assert isinstance(output, str)
    recorded = json.loads(output)
    assert recorded["status"] == "In Review"
    assert [step["status"] for step in recorded["steps"]] == [
        "Failed",
        "Skipped",
        "Skipped",
        "Skipped",
        "Skipped",
        "Skipped",
        "Skipped",
        "Skipped",
    ]


@pytest.mark.parametrize(
    "has_public_key,has_secret_key,enabled",
    [
        (False, False, "true"),
        (True, False, "true"),
        (False, True, "true"),
        (True, True, "false"),
    ],
)
def test_incomplete_or_disabled_configuration_has_no_trace_link(
    matching_company: UUID,
    matching_fields: InvoiceFields,
    database_url: str,
    erp_tools: ERPTools,
    trace_capture: tuple[Langfuse, InMemorySpanExporter, str],
    monkeypatch: pytest.MonkeyPatch,
    has_public_key: bool,
    has_secret_key: bool,
    enabled: str,
) -> None:
    tracing, exporter, public_key = trace_capture
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", public_key if has_public_key else "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test" if has_secret_key else "")
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", enabled)
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(matching_fields),
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
        tracing=configured_tracing(),
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
    tracing.flush()

    assert result.status == "Auto-Approved"
    assert result.trace_url is None
    assert exporter.get_finished_spans() == ()


@pytest.mark.parametrize("project_status", [503])
def test_unavailable_langfuse_does_not_stop_invoice_processing(
    matching_company: UUID,
    matching_fields: InvoiceFields,
    database_url: str,
    erp_tools: ERPTools,
    trace_capture: tuple[Langfuse, InMemorySpanExporter, str],
) -> None:
    tracing, exporter, public_key = trace_capture
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(matching_fields),
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
        tracing=RunTracing(tracing, public_key=public_key),
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

    assert result.status == "Auto-Approved"
    assert result.trace_url is None
    saved = processing.get(matching_company, uploaded.id)
    assert saved is not None
    assert saved.status == "Auto-Approved"
    assert saved.trace_url is None


@pytest.mark.parametrize(
    "provider,model",
    [
        ("openai", "gpt-4.1-mini"),
        ("anthropic", "claude-haiku-4-5-20251001"),
    ],
)
def test_reading_and_pairing_models_record_tokens_and_time_in_the_same_trace(
    matching_company: UUID,
    matching_fields: InvoiceFields,
    database_url: str,
    erp_tools: ERPTools,
    trace_capture: tuple[Langfuse, InMemorySpanExporter, str],
    model_api: tuple[str, list[dict[str, object]]],
    monkeypatch: pytest.MonkeyPatch,
    provider: Literal["openai", "anthropic"],
    model: str,
) -> None:
    base_url, responses = model_api
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_API_BASE", base_url)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")
    monkeypatch.setenv("ANTHROPIC_API_URL", base_url)
    supplier = erp_tools.find_supplier(matching_company, "Paper & Co.")
    assert supplier is not None
    purchase_order = erp_tools.get_purchase_order(
        matching_company, supplier.id, "PO-1002"
    )
    assert purchase_order is not None
    line = matching_fields.lines[0].model_copy(
        update={"description": "A4 recycled paper in boxes"}
    )
    fields = matching_fields.model_copy(update={"lines": [line]})
    responses.extend(
        [
            {"invoice": fields.model_dump(mode="json")},
            {"purchase_order_line_id": str(purchase_order.lines[0].id)},
        ]
    )
    tracing, exporter, public_key = trace_capture
    processing = InvoiceProcessing(
        database_url,
        reader=VisionInvoiceReader(provider, model),
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
        line_pairer=ModelLinePairer(provider, model),
        tracing=RunTracing(tracing, public_key=public_key),
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
    tracing.flush()

    assert result.status == "Auto-Approved"
    assert result.comparison[0].paired_by == "meaning"
    assert result.trace_url is not None
    spans = exporter.get_finished_spans()
    trace_id = int(result.trace_url.rsplit("/", 1)[-1], 16)
    assert {span.context.trace_id for span in spans if span.context} == {trace_id}
    generations = [
        span
        for span in spans
        if span.attributes
        and span.attributes.get("langfuse.observation.type") == "generation"
    ]
    assert len(generations) == 2
    for generation in generations:
        assert generation.attributes is not None
        assert generation.attributes["langfuse.observation.model.name"] == model
        usage = generation.attributes["langfuse.observation.usage_details"]
        assert isinstance(usage, str)
        tokens = json.loads(usage)
        assert tokens["input"] == 20
        assert tokens["output"] == 10
        if "total" in tokens:
            assert tokens["total"] == 30
        assert generation.start_time is not None
        assert generation.end_time is not None
        assert generation.end_time > generation.start_time
    assert any(
        span.name == "search_purchase_order_lines"
        and span.attributes
        and span.attributes.get("langfuse.observation.type") == "tool"
        for span in spans
    )
