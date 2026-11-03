import json
from pathlib import Path
from shutil import copytree
from uuid import UUID

import pytest
import time_machine

from evals.decisions import DEFAULT_SAMPLE, DecisionCase, evaluate_decisions, main
from invoice_agent.clients.invoice_reader import ScriptedInvoiceReader
from invoice_agent.schemas.invoice_fields import InvoiceFields
from invoice_agent.schemas.invoices import InvoiceFile
from invoice_agent.services.daily_ai_limit import DailyAILimit
from invoice_agent.services.erp_tools import ERPTools
from invoice_agent.services.invoice_processing import InvoiceProcessing


def test_correct_auto_approval_is_scored_through_invoice_processing(
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
    case = DecisionCase(
        case_id="clean-auto-approval",
        document=InvoiceFile(
            filename="invoice.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4\nInvoice",
        ),
        expected_status="Auto-Approved",
        expected_reasons=[],
    )

    report = evaluate_decisions(
        processing,
        matching_company,
        [case],
        sample_version="test-v1",
        model="fake",
    )

    assert report.correct == 1
    assert report.total == 1
    assert report.accuracy == 1.0
    assert report.wrong_auto_approvals == 0
    stored = processing.get(matching_company, report.invoices[0].invoice_id)
    assert stored is not None
    assert stored.status == "Auto-Approved"


def test_eval_command_runs_every_rule_and_saves_the_decisions(
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
    assert "Decision accuracy: 14/14 (100.00%)" in output
    assert "Wrong Auto-Approvals: 0" in output
    result_files = list(tmp_path.glob("decisions-*.json"))
    assert len(result_files) == 1
    saved = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert saved["evaluated_at"] == "2026-11-03T10:00:00Z"
    assert saved["sample_version"] == "synthetic-decisions-v1"
    assert saved["model"] == "fake-decision-v1"
    assert saved["correct"] == 14
    assert saved["total"] == 14
    assert saved["accuracy"] == 1.0
    assert saved["wrong_auto_approvals"] == 0
    assert {invoice["case_id"] for invoice in saved["invoices"]} == {
        "clean-auto-approval",
        "price-over-tolerance",
        "lower-price",
        "quantity-mismatch",
        "partial-delivery",
        "received-more-than-ordered",
        "wording-differences",
        "missing-purchase-order",
        "missing-goods-receipt",
        "duplicate-invoice",
        "possible-duplicate",
        "unknown-supplier",
        "total-over-limit",
        "unmatched-line",
    }


@pytest.mark.parametrize("check_baseline", [False, True])
def test_wrong_auto_approval_fails_even_when_the_baseline_accepts_it(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    check_baseline: bool,
) -> None:
    sample_dir = copytree(DEFAULT_SAMPLE, tmp_path / "sample")
    manifest_path = sample_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    case = next(
        case for case in manifest["cases"] if case["case_id"] == "quantity-mismatch"
    )
    case["invoice_updates"] = {}
    manifest["cases"] = [case]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    baseline = {
        "sample_version": "synthetic-decisions-v1",
        "model": "fake-decision-v1",
        "correct": 0,
        "total": 1,
        "accuracy": 0.0,
        "wrong_auto_approvals": 1,
        "decisions": {"quantity-mismatch": {"status": "Auto-Approved", "reasons": []}},
    }
    (sample_dir / "baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)
    output_dir = tmp_path / "results"
    arguments = ["--sample-dir", str(sample_dir), "--output-dir", str(output_dir)]
    if check_baseline:
        arguments.append("--check")

    exit_code = main(arguments)

    assert exit_code == 1
    output = capsys.readouterr()
    assert "Wrong Auto-Approvals: 1" in output.out
    assert "Wrong Auto-Approvals must be zero." in output.err
    result_files = list(output_dir.glob("decisions-*.json"))
    assert len(result_files) == 1
    saved = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert saved["correct"] == 0
    assert saved["wrong_auto_approvals"] == 1


@pytest.mark.parametrize("change", ["overall", "status", "reasons", "case-id"])
def test_changed_baseline_fails_and_keeps_the_report(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    change: str,
) -> None:
    sample_dir = copytree(DEFAULT_SAMPLE, tmp_path / "sample")
    baseline_path = sample_dir / "baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    if change == "overall":
        baseline["correct"] = 13
        baseline["accuracy"] = 13 / 14
    elif change == "status":
        baseline["decisions"]["clean-auto-approval"]["status"] = "In Review"
    elif change == "reasons":
        baseline["decisions"]["unknown-supplier"]["reasons"] = ["Changed reason"]
    else:
        baseline["decisions"]["renamed-case"] = baseline["decisions"].pop(
            "unknown-supplier"
        )
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
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
    result_files = list(output_dir.glob("decisions-*.json"))
    assert len(result_files) == 1
    saved = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert saved["correct"] == 14
    assert saved["wrong_auto_approvals"] == 0
