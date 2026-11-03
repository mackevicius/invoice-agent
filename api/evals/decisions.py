import argparse
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from invoice_agent.clients.embeddings import ScriptedEmbeddings
from invoice_agent.clients.invoice_reader import ScriptedInvoiceReader
from invoice_agent.clients.line_pairing import ScriptedLinePairer
from invoice_agent.db.initialize import initialize_database
from invoice_agent.db.seed import configure_decision_receipt
from invoice_agent.schemas.invoice_fields import InvoiceFields
from invoice_agent.schemas.invoices import InvoiceFile
from invoice_agent.services.daily_ai_limit import DailyAILimit
from invoice_agent.services.demo_company import DemoCompanies
from invoice_agent.services.erp_tools import ERPTools
from invoice_agent.services.invoice_processing import InvoiceProcessing

DEFAULT_SAMPLE = Path(__file__).parent / "data" / "decisions-v1"


class DecisionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["Auto-Approved", "In Review"]
    reasons: list[str]


class SampleCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    invoice_updates: dict[str, JsonValue] = Field(default_factory=dict)
    received_quantity: Decimal | None = Field(default=Decimal("24"), ge=0)
    pairing_choices: dict[str, str | None] = Field(default_factory=dict)
    expected: DecisionOutcome


class DecisionSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    model: str = Field(min_length=1)
    base_invoice: InvoiceFields
    cases: list[SampleCase] = Field(min_length=1)


@dataclass(frozen=True)
class DecisionCase:
    case_id: str
    document: InvoiceFile
    expected_status: Literal["Auto-Approved", "In Review"]
    expected_reasons: list[str]


class InvoiceDecision(BaseModel):
    case_id: str
    invoice_id: UUID
    expected_status: str
    actual_status: str
    expected_reasons: list[str]
    actual_reasons: list[str]
    correct: bool


class DecisionReport(BaseModel):
    evaluated_at: datetime
    sample_version: str
    sample_sha256: str | None = None
    model: str
    correct: int
    total: int
    accuracy: float
    wrong_auto_approvals: int
    invoices: list[InvoiceDecision]


class DecisionBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_version: str
    model: str
    correct: int
    total: int
    accuracy: float
    wrong_auto_approvals: int
    decisions: dict[str, DecisionOutcome]


def evaluate_decisions(
    processing: InvoiceProcessing,
    company_id: UUID,
    cases: list[DecisionCase],
    *,
    sample_version: str,
    model: str,
) -> DecisionReport:
    invoices: list[InvoiceDecision] = []
    for case in cases:
        uploaded = processing.upload(company_id, case.document)
        result = processing.process(company_id, uploaded.id)
        invoices.append(
            InvoiceDecision(
                case_id=case.case_id,
                invoice_id=result.id,
                expected_status=case.expected_status,
                actual_status=result.status,
                expected_reasons=case.expected_reasons,
                actual_reasons=result.reasons,
                correct=(
                    result.status == case.expected_status
                    and result.reasons == case.expected_reasons
                ),
            )
        )
    return _build_report(invoices, sample_version=sample_version, model=model)


def _build_report(
    invoices: list[InvoiceDecision], *, sample_version: str, model: str
) -> DecisionReport:
    correct = sum(invoice.correct for invoice in invoices)
    return DecisionReport(
        evaluated_at=datetime.now(UTC),
        sample_version=sample_version,
        model=model,
        correct=correct,
        total=len(invoices),
        accuracy=correct / len(invoices),
        wrong_auto_approvals=sum(
            invoice.actual_status == "Auto-Approved"
            and invoice.expected_status != "Auto-Approved"
            for invoice in invoices
        ),
        invoices=invoices,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score synthetic Invoice decisions.")
    parser.add_argument("--sample-dir", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--output-dir", type=Path, default=Path("evals/results"))
    parser.add_argument(
        "--check", action="store_true", help="Check the saved baseline."
    )
    arguments = parser.parse_args(argv)
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        parser.error("Set TEST_DATABASE_URL to a Postgres database with pgvector.")
    try:
        manifest_bytes = (arguments.sample_dir / "manifest.json").read_bytes()
        sample = DecisionSample.model_validate_json(manifest_bytes)
        if len({case.case_id for case in sample.cases}) != len(sample.cases):
            raise ValueError("Decision sample case IDs must be unique.")
        initialize_database(database_url)
        embeddings = ScriptedEmbeddings()
        companies = DemoCompanies(database_url, embeddings)
        erp_tools = ERPTools(database_url, embeddings)
        invoices: list[InvoiceDecision] = []
        for case in sample.cases:
            fields = InvoiceFields.model_validate(
                sample.base_invoice.model_dump() | case.invoice_updates
            )
            company = companies.start(None).company
            if case.received_quantity != Decimal("24"):
                with psycopg.connect(database_url) as connection:
                    configure_decision_receipt(
                        connection, company.id, case.received_quantity
                    )
            processing = InvoiceProcessing(
                database_url,
                reader=ScriptedInvoiceReader(fields),
                erp_tools=erp_tools,
                daily_ai_limit=DailyAILimit(database_url),
                line_pairer=ScriptedLinePairer(case.pairing_choices),
            )
            report = evaluate_decisions(
                processing,
                company.id,
                [
                    DecisionCase(
                        case_id=case.case_id,
                        document=InvoiceFile(
                            filename=f"{case.case_id}.pdf",
                            content_type="application/pdf",
                            content=b"%PDF-1.4\nSynthetic decision evaluation",
                        ),
                        expected_status=case.expected.status,
                        expected_reasons=case.expected.reasons,
                    )
                ],
                sample_version=sample.version,
                model=sample.model,
            )
            invoices.extend(report.invoices)
        report = _build_report(
            invoices, sample_version=sample.version, model=sample.model
        )
        report.sample_sha256 = sha256(manifest_bytes).hexdigest()
        arguments.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = report.evaluated_at.strftime("%Y%m%dT%H%M%S%fZ")
        path = arguments.output_dir / f"decisions-{timestamp}-{uuid4().hex}.json"
        with path.open("x", encoding="utf-8") as destination:
            destination.write(report.model_dump_json(indent=2) + "\n")
        print(
            f"Decision accuracy: {report.correct}/{report.total} "
            f"({report.accuracy:.2%})"
        )
        print(f"Wrong Auto-Approvals: {report.wrong_auto_approvals}")
        print(f"Saved: {path}")
        if report.wrong_auto_approvals:
            print("Wrong Auto-Approvals must be zero.", file=sys.stderr)
            return 1
        if arguments.check:
            baseline = DecisionBaseline.model_validate_json(
                (arguments.sample_dir / "baseline.json").read_bytes()
            )
            actual = DecisionBaseline(
                sample_version=report.sample_version,
                model=report.model,
                correct=report.correct,
                total=report.total,
                accuracy=report.accuracy,
                wrong_auto_approvals=report.wrong_auto_approvals,
                decisions={
                    invoice.case_id: DecisionOutcome.model_validate(
                        {
                            "status": invoice.actual_status,
                            "reasons": invoice.actual_reasons,
                        }
                    )
                    for invoice in report.invoices
                },
            )
            if actual != baseline:
                print(
                    "Decision results do not match the saved baseline.", file=sys.stderr
                )
                return 1
        return 0
    except (OSError, ValueError) as error:
        print(f"Decision evaluation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
