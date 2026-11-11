import json
from collections.abc import Callable, Iterator
from pathlib import Path
from shutil import copytree
from typing import Literal
from uuid import UUID, uuid4

import httpx
import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from evals.compare import main as compare_main
from evals.decisions import DEFAULT_SAMPLE as DECISION_SAMPLE
from evals.decisions import DecisionCase, evaluate_decisions
from evals.decisions import main as decisions_main
from evals.reading import DEFAULT_SAMPLE, ReadingCase, ReadingLabels, evaluate_reading
from evals.reading import main as reading_main
from invoice_agent.clients.embeddings import ScriptedEmbeddings
from invoice_agent.clients.invoice_reader import ScriptedInvoiceReader
from invoice_agent.clients.tracing import RunTracing
from invoice_agent.schemas.invoice_fields import InvoiceFields
from invoice_agent.schemas.invoices import InvoiceFile
from invoice_agent.services.daily_ai_limit import DailyAILimit
from invoice_agent.services.erp_tools import ERPTools
from invoice_agent.services.invoice_processing import InvoiceProcessing


@pytest.fixture
def invoice_document() -> InvoiceFile:
    return InvoiceFile(
        filename="invoice.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4\nInvoice",
    )


@pytest.fixture
def eval_tracing(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[RunTracing, list[httpx.Response]]]:
    pages: list[httpx.Response] = []
    ticks = iter(range(0, 1000, 5))
    monkeypatch.setattr("evals.reporting.monotonic", lambda: float(next(ticks)))
    monkeypatch.setattr("evals.reporting.sleep", lambda seconds: None)

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/projects"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "eval-project",
                            "name": "Eval tests",
                            "organization": {"id": "test-org", "name": "Tests"},
                            "metadata": {},
                        }
                    ]
                },
            )
        if request.url.path.endswith("/observations"):
            return pages.pop(0) if len(pages) > 1 else pages[0]
        return httpx.Response(404, json={"message": "Media is disabled in tests."})

    public_key = f"pk-lf-eval-{uuid4()}"
    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        client = Langfuse(
            public_key=public_key,
            secret_key="sk-lf-test",
            base_url="https://langfuse.test",
            httpx_client=http_client,
            tracer_provider=TracerProvider(),
            span_exporter=InMemorySpanExporter(),
        )
        try:
            yield RunTracing(client, public_key=public_key), pages
        finally:
            client.shutdown()


def observation_page(
    cost_usd: float | None,
    seconds: int,
    *,
    parent_observation_id: str | None = None,
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": [
                {
                    "id": "invoice-run",
                    "project_id": "eval-project",
                    "type": "SPAN",
                    "name": "Invoice run",
                    "parent_observation_id": parent_observation_id,
                    "start_time": "2026-11-03T10:00:00Z",
                    "end_time": f"2026-11-03T10:00:{seconds:02d}Z",
                },
                {
                    "id": "model-call",
                    "project_id": "eval-project",
                    "type": "GENERATION",
                    "parent_observation_id": "invoice-run",
                    "start_time": "2026-11-03T10:00:00Z",
                    "end_time": f"2026-11-03T10:00:{seconds:02d}Z",
                    "total_cost": cost_usd,
                },
            ],
            "meta": {},
        },
    )


@pytest.fixture
def live_settings(
    monkeypatch: pytest.MonkeyPatch,
    model_api: tuple[str, list[dict[str, object]]],
    eval_tracing: tuple[RunTracing, list[httpx.Response]],
) -> None:
    base_url, _ = model_api
    tracing, _ = eval_tracing
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("OPENAI_BASE_URL", f"{base_url}/v1")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", base_url)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", tracing.public_key or "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://langfuse.test")
    monkeypatch.setattr(
        "invoice_agent.clients.embeddings.TextEmbedding",
        lambda **settings: ScriptedEmbeddings(),
    )


@pytest.mark.parametrize("parent_observation_id", [None, "upstream-span"])
def test_reading_report_averages_cost_and_time_from_langfuse(
    parent_observation_id: str | None,
    matching_company: UUID,
    invoice_document: InvoiceFile,
    matching_fields: InvoiceFields,
    database_url: str,
    erp_tools: ERPTools,
    eval_tracing: tuple[RunTracing, list[httpx.Response]],
) -> None:
    tracing, pages = eval_tracing
    pages.extend(
        [
            observation_page(0.01, 2, parent_observation_id=parent_observation_id),
            observation_page(0.03, 4, parent_observation_id=parent_observation_id),
        ]
    )
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(matching_fields),
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
        tracing=tracing,
    )

    report = evaluate_reading(
        processing,
        matching_company,
        [
            ReadingCase(
                case_id=f"measured-{position}",
                document=invoice_document,
                expected=ReadingLabels(total=matching_fields.total),
            )
            for position in range(2)
        ],
        sample_version="test-v1",
        model="test-model",
    )

    assert report.average_cost_usd == pytest.approx(0.02)
    assert report.average_time_seconds == pytest.approx(3.0)
    assert report.invoices[0].cost_usd == pytest.approx(0.01)
    assert report.invoices[1].time_seconds == pytest.approx(4.0)
    assert all(invoice.trace_url is not None for invoice in report.invoices)


def test_decision_report_includes_cost_and_time_from_langfuse(
    matching_company: UUID,
    invoice_document: InvoiceFile,
    matching_fields: InvoiceFields,
    database_url: str,
    erp_tools: ERPTools,
    eval_tracing: tuple[RunTracing, list[httpx.Response]],
) -> None:
    tracing, pages = eval_tracing
    pages.append(observation_page(0.04, 8))
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(matching_fields),
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
        tracing=tracing,
    )

    report = evaluate_decisions(
        processing,
        matching_company,
        [
            DecisionCase(
                case_id="measured-decision",
                document=invoice_document,
                expected_status="Auto-Approved",
                expected_reasons=[],
            )
        ],
        sample_version="test-v1",
        model="test-model",
    )

    assert report.correct == 1
    assert report.average_cost_usd == pytest.approx(0.04)
    assert report.average_time_seconds == pytest.approx(8.0)
    assert report.invoices[0].cost_usd == pytest.approx(0.04)


def test_missing_langfuse_price_is_not_reported_as_zero(
    matching_company: UUID,
    invoice_document: InvoiceFile,
    matching_fields: InvoiceFields,
    database_url: str,
    erp_tools: ERPTools,
    eval_tracing: tuple[RunTracing, list[httpx.Response]],
) -> None:
    tracing, pages = eval_tracing
    pages.append(observation_page(None, 2))
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(matching_fields),
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
        tracing=tracing,
    )

    report = evaluate_reading(
        processing,
        matching_company,
        [
            ReadingCase(
                case_id="missing-price",
                document=invoice_document,
                expected=ReadingLabels(total=matching_fields.total),
            )
        ],
        sample_version="test-v1",
        model="unpriced-model",
    )

    assert report.average_cost_usd is None
    assert report.average_time_seconds == pytest.approx(2.0)
    assert report.invoices[0].metrics_error is not None
    assert "cost" in report.invoices[0].metrics_error.lower()


def test_report_waits_for_observations_and_includes_every_page(
    matching_company: UUID,
    invoice_document: InvoiceFile,
    matching_fields: InvoiceFields,
    database_url: str,
    erp_tools: ERPTools,
    eval_tracing: tuple[RunTracing, list[httpx.Response]],
) -> None:
    tracing, pages = eval_tracing
    observations = observation_page(0.01, 3).json()["data"]
    second_generation = observation_page(0.02, 3).json()["data"][1]
    second_generation["id"] = "second-model-call"
    pages.extend(
        [
            httpx.Response(200, json={"data": [], "meta": {}}),
            httpx.Response(
                200, json={"data": observations[:1], "meta": {"cursor": "next"}}
            ),
            httpx.Response(
                200, json={"data": observations[1:], "meta": {"cursor": "last"}}
            ),
            httpx.Response(200, json={"data": [second_generation], "meta": {}}),
        ]
    )
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(matching_fields),
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
        tracing=tracing,
    )

    report = evaluate_reading(
        processing,
        matching_company,
        [
            ReadingCase(
                case_id="delayed-trace",
                document=invoice_document,
                expected=ReadingLabels(total=matching_fields.total),
            )
        ],
        sample_version="test-v1",
        model="test-model",
    )

    assert report.average_cost_usd == pytest.approx(0.03)
    assert report.average_time_seconds == pytest.approx(3.0)
    assert report.invoices[0].metrics_error is None


@pytest.mark.parametrize("delay", ["none", "arrives", "timeout"])
@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_reading_command_uses_the_chosen_live_provider_and_saves_measurements(
    delay: Literal["none", "arrives", "timeout"],
    provider: Literal["openai", "anthropic"],
    database_url: str,
    matching_fields: InvoiceFields,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    model_api: tuple[str, list[dict[str, object]]],
    eval_tracing: tuple[RunTracing, list[httpx.Response]],
    live_settings: None,
) -> None:
    sample_dir = copytree(DEFAULT_SAMPLE, tmp_path / "sample")
    manifest_path = sample_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["cases"] = manifest["cases"][:1]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (sample_dir / "fake.json").unlink()
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)
    _, responses = model_api
    responses.append({"invoice": matching_fields.model_dump(mode="json")})
    _, pages = eval_tracing
    if delay != "none":
        ticks = iter(range(0, 120, 5))
        monkeypatch.setattr(
            "evals.reporting.monotonic", lambda: float(next(ticks)), raising=False
        )
        monkeypatch.setattr("evals.reporting.sleep", lambda seconds: None)
        root_only = observation_page(0.005, 2).json()["data"][:1]
        pages.extend(
            httpx.Response(200, json={"data": root_only, "meta": {}})
            for _ in range(20 if delay == "timeout" else 7)
        )
    pages.append(observation_page(0.005, 2))
    output_dir = tmp_path / "results"

    exit_code = reading_main(
        [
            "--provider",
            provider,
            "--model",
            "test-live-model",
            "--sample-dir",
            str(sample_dir),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == (1 if delay == "timeout" else 0)
    saved = json.loads(next(output_dir.glob("reading-*.json")).read_text())
    assert saved["provider"] == provider
    assert saved["model"] == "test-live-model"
    assert saved["invoices"][0]["actual"]["supplier_name"] == "Paper & Co."
    if delay == "timeout":
        assert saved["average_cost_usd"] is None
        assert saved["invoices"][0]["metrics_error"] is not None
    else:
        assert saved["average_cost_usd"] == pytest.approx(0.005)
    assert saved["average_time_seconds"] == pytest.approx(2.0)
    assert saved["sample_sha256"] is not None


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("case_id", ["unmatched-line", "clean-auto-approval"])
def test_decision_command_uses_live_pairing_instead_of_scripted_choices(
    provider: Literal["openai", "anthropic"],
    case_id: str,
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    model_api: tuple[str, list[dict[str, object]]],
    eval_tracing: tuple[RunTracing, list[httpx.Response]],
    live_settings: None,
) -> None:
    sample_dir = copytree(DECISION_SAMPLE, tmp_path / "sample")
    manifest_path = sample_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected = next(case for case in manifest["cases"] if case["case_id"] == case_id)
    selected["pairing_choices"] = {"Extra packing charge": "Recycled A4 paper, box"}
    manifest["cases"] = [selected]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)
    _, responses = model_api
    if case_id == "unmatched-line":
        responses.append({"purchase_order_line_id": None})
    _, pages = eval_tracing
    page = observation_page(0.006, 3)
    if case_id == "clean-auto-approval":
        page = httpx.Response(200, json={"data": page.json()["data"][:1], "meta": {}})
    pages.append(page)
    output_dir = tmp_path / "results"

    exit_code = decisions_main(
        [
            "--provider",
            provider,
            "--model",
            "test-live-model",
            "--sample-dir",
            str(sample_dir),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    saved = json.loads(next(output_dir.glob("decisions-*.json")).read_text())
    assert saved["provider"] == provider
    assert saved["model"] == "test-live-model"
    assert saved["correct"] == 1
    assert saved["wrong_auto_approvals"] == 0
    assert saved["average_cost_usd"] == pytest.approx(
        0.006 if case_id == "unmatched-line" else 0
    )
    assert saved["average_time_seconds"] == pytest.approx(3.0)


@pytest.mark.parametrize("evaluation", ["reading", "decisions"])
def test_live_commands_save_incomplete_measurements_and_fail(
    evaluation: Literal["reading", "decisions"],
    database_url: str,
    matching_fields: InvoiceFields,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    model_api: tuple[str, list[dict[str, object]]],
    eval_tracing: tuple[RunTracing, list[httpx.Response]],
    live_settings: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = DEFAULT_SAMPLE if evaluation == "reading" else DECISION_SAMPLE
    sample_dir = copytree(source, tmp_path / "sample")
    manifest_path = sample_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["cases"] = manifest["cases"][:1]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)
    if evaluation == "reading":
        _, responses = model_api
        responses.append({"invoice": matching_fields.model_dump(mode="json")})
    _, pages = eval_tracing
    pages.append(observation_page(None, 2))
    output_dir = tmp_path / "results"
    command = reading_main if evaluation == "reading" else decisions_main

    exit_code = command(
        [
            "--provider",
            "openai",
            "--sample-dir",
            str(sample_dir),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 1
    assert "Langfuse measurements are incomplete" in capsys.readouterr().err
    saved = json.loads(next(output_dir.glob("*.json")).read_text())
    assert saved["average_cost_usd"] is None
    assert saved["average_time_seconds"] == pytest.approx(2.0)
    assert saved["invoices"][0]["metrics_error"] is not None


def test_saved_model_reports_can_be_compared_side_by_side(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)
    assert reading_main(["--output-dir", str(tmp_path), "--check"]) == 0
    first_path = next(tmp_path.glob("reading-*.json"))
    first = json.loads(first_path.read_text())
    first.update(
        provider="openai",
        model="model-a",
        average_cost_usd=0.02,
        average_time_seconds=3.0,
    )
    first_path.write_text(json.dumps(first), encoding="utf-8")
    second_path = tmp_path / "model-b.json"
    second = first | {
        "provider": "anthropic",
        "model": "model-b",
        "average_cost_usd": 0.01,
        "average_time_seconds": 4.0,
    }
    second_path.write_text(json.dumps(second), encoding="utf-8")
    capsys.readouterr()

    exit_code = compare_main([str(tmp_path)])

    assert exit_code == 0
    output = capsys.readouterr().out
    header = next(line for line in output.splitlines() if line.startswith("| Metric"))
    assert "openai/model-a" in header
    assert "anthropic/model-b" in header
    assert "71.11%" in output
    assert "$0.020000" in output
    assert "$0.010000" in output
    assert "3.000 s" in output
    assert "4.000 s" in output


@pytest.mark.parametrize("command", [reading_main, decisions_main])
@pytest.mark.parametrize(
    "arguments",
    [["--provider", "openai", "--check"], ["--model", "not-a-fake"]],
)
def test_commands_reject_mixing_live_models_and_fake_baseline_options(
    command: Callable[[list[str] | None], int], arguments: list[str]
) -> None:
    with pytest.raises(SystemExit) as error:
        command(arguments)
    assert error.value.code == 2
