import json
from decimal import Decimal
from pathlib import Path
from shutil import copytree
from uuid import UUID

import pytest
import time_machine

from evals.reading import (
    DEFAULT_SAMPLE,
    ReadingCase,
    ReadingLabels,
    ReadingLineLabels,
    evaluate_reading,
    main,
)
from invoice_agent.clients.invoice_reader import ScriptedInvoiceReader
from invoice_agent.schemas.invoice_fields import InvoiceFields
from invoice_agent.schemas.invoices import InvoiceFile
from invoice_agent.services.daily_ai_limit import DailyAILimit
from invoice_agent.services.erp_tools import ERPTools
from invoice_agent.services.invoice_processing import InvoiceProcessing


def test_report_separates_failed_reads_from_text_and_value_mismatches(
    matching_company: UUID,
    matching_fields: InvoiceFields,
    openai_processing: InvoiceProcessing,
    model_api: tuple[str, list[dict[str, object]]],
) -> None:
    _, responses = model_api
    different_fields = matching_fields.model_copy(
        update={"supplier_name": "Paper&Co.", "total": Decimal("3214.09")}
    )
    invalid_fields = matching_fields.model_dump(mode="json")
    invalid_fields["lines"][0]["unexpected"] = "field"
    responses.extend(
        [
            {"invoice": different_fields.model_dump(mode="json")},
            {"invoice": invalid_fields},
            {"invoice": None},
        ]
    )
    cases = [
        ReadingCase(
            case_id=f"diagnostic-{position}",
            document=InvoiceFile(
                filename=f"invoice-{position}.png",
                content_type="image/png",
                content=b"Invoice image",
            ),
            expected=ReadingLabels.model_validate(matching_fields.model_dump()),
        )
        for position in range(3)
    ]

    report = evaluate_reading(
        openai_processing,
        matching_company,
        cases,
        sample_version="test-v1",
        model="test-model",
    )

    assert report.overall.correct == 9
    assert report.overall.total == 33
    assert report.diagnostics is not None
    assert report.diagnostics.model_dump() == {
        "invoices_with_fields": 1,
        "invoices_without_fields": 2,
        "invalid_responses": 1,
        "failed_read_fields": 22,
        "text_mismatches": 1,
        "value_mismatches": 1,
    }
    assert report.invoices[1].read_failure == "invalid_response"
    assert report.invoices[2].read_failure == "no_fields"


def test_wrong_total_reduces_reading_accuracy(
    matching_company: UUID,
    matching_fields: InvoiceFields,
    database_url: str,
    erp_tools: ERPTools,
) -> None:
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(
            matching_fields.model_copy(update={"total": Decimal("3214.09")})
        ),
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
    )
    case = ReadingCase(
        case_id="wrong-total",
        document=InvoiceFile(
            filename="invoice.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4\nInvoice",
        ),
        expected=ReadingLabels.model_validate(matching_fields.model_dump()),
    )

    report = evaluate_reading(
        processing,
        matching_company,
        [case],
        sample_version="test-v1",
        model="fake",
    )

    assert report.per_field["total"].correct == 0
    assert report.per_field["total"].total == 1
    assert report.per_field["supplier_name"].accuracy == 1.0
    assert report.overall.correct == 10
    assert report.overall.total == 11
    assert report.overall.accuracy == pytest.approx(10 / 11)
    stored = processing.get(matching_company, report.invoices[0].invoice_id)
    assert stored is not None
    assert stored.total == Decimal("3214.09")


def test_unlabelled_fields_do_not_reduce_accuracy(
    matching_company: UUID,
    matching_fields: InvoiceFields,
    database_url: str,
    erp_tools: ERPTools,
) -> None:
    processing = InvoiceProcessing(
        database_url,
        reader=ScriptedInvoiceReader(matching_fields),
        erp_tools=erp_tools,
        daily_ai_limit=DailyAILimit(database_url),
    )
    case = ReadingCase(
        case_id="partial-labels",
        document=InvoiceFile(
            filename="invoice.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4\nInvoice",
        ),
        expected=ReadingLabels(
            supplier_name="Paper & Co.",
            total=Decimal("3214.08"),
            lines=[
                ReadingLineLabels(
                    description="Recycled A4 paper, box", quantity=Decimal("24")
                )
            ],
        ),
    )

    report = evaluate_reading(
        processing,
        matching_company,
        [case],
        sample_version="test-v1",
        model="fake",
    )

    assert report.per_field.keys() == {
        "supplier_name",
        "total",
        "lines.description",
        "lines.quantity",
    }
    assert report.overall.correct == 4
    assert report.overall.total == 4
    assert report.overall.accuracy == 1.0


def test_eval_command_scores_and_saves_the_fixed_sample(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)

    with time_machine.travel("2026-11-03T10:00:00Z", tick=False):
        exit_code = main(["--output-dir", str(tmp_path), "--check"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "total: 1/3 (33.33%)" in output
    assert "Overall: 32/45 (71.11%)" in output
    result_files = list(tmp_path.glob("*.json"))
    assert len(result_files) == 1
    saved = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert saved["sample_version"] == "kaggle-ocr-v3-first3-v1"
    assert saved["model"] == "fake-reading-v1"
    assert saved["evaluated_at"] == "2026-11-03T10:00:00Z"
    assert saved["overall"]["correct"] == 32
    assert saved["overall"]["total"] == 45
    assert saved["overall"]["accuracy"] == pytest.approx(32 / 45)
    assert saved["average_cost_usd"] is None
    assert saved["average_time_seconds"] is None
    assert len(saved["invoices"]) == 3
    assert saved["invoices"][2]["actual"] is None


def test_check_rejects_changed_field_scores_and_keeps_the_report(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sample_dir = copytree(DEFAULT_SAMPLE, tmp_path / "sample")
    fixture_path = sample_dir / "fake.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture["expected_per_field"]["total"]["correct"] = 2
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)
    output_dir = tmp_path / "results"

    exit_code = main(
        [
            "--sample-dir",
            str(sample_dir),
            "--output-dir",
            str(output_dir),
            "--check",
        ]
    )

    assert exit_code == 1
    assert "do not match the saved baseline" in capsys.readouterr().err
    assert len(list(output_dir.glob("*.json"))) == 1


def test_changed_image_is_rejected_before_processing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sample_dir = copytree(DEFAULT_SAMPLE, tmp_path / "sample")
    (sample_dir / "batch1-0001.jpg").write_bytes(b"changed image")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://not-used")
    output_dir = tmp_path / "results"

    exit_code = main(["--sample-dir", str(sample_dir), "--output-dir", str(output_dir)])

    assert exit_code == 1
    assert "checksum mismatch: batch1-0001.jpg" in capsys.readouterr().err
    assert not output_dir.exists()


def test_eval_command_scores_generated_pngs_and_pdfs(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)
    sample_dir = DEFAULT_SAMPLE.parent / "generated-v1"

    exit_code = main(
        [
            "--sample-dir",
            str(sample_dir),
            "--output-dir",
            str(tmp_path),
            "--check",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "total: 3/4 (75.00%)" in output
    assert "Overall: 83/84 (98.81%)" in output
    result_files = list(tmp_path.glob("*.json"))
    assert len(result_files) == 1
    saved = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert saved["sample_version"] == "generated-invoices-v1"
    assert saved["sample_source"]["kind"] == "synthetic"
    assert saved["model"] == "fake-generated-v1"
    assert saved["overall"]["correct"] == 83
    assert saved["overall"]["total"] == 84
    assert {invoice["case_id"] for invoice in saved["invoices"]} == {
        "generated-png-clean",
        "generated-png-compact",
        "generated-pdf-single-page",
        "generated-pdf-multi-page",
    }
    assert len(saved["invoices"][3]["expected"]["lines"]) == 6
    assert saved["invoices"][3]["actual"]["total"] == "240.00"
