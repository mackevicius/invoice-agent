import argparse
import os
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_serializer

from invoice_agent.clients.embeddings import ScriptedEmbeddings
from invoice_agent.db.initialize import initialize_database
from invoice_agent.schemas.invoice_fields import InvoiceFields
from invoice_agent.schemas.invoices import InvoiceFile
from invoice_agent.services.daily_ai_limit import DailyAILimit
from invoice_agent.services.demo_company import DemoCompanies
from invoice_agent.services.erp_tools import ERPTools
from invoice_agent.services.invoices import InvoiceProcessing

DEFAULT_SAMPLE = Path(__file__).parent / "data" / "reading-v1"


class ReadingLineLabels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    item_code: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None


class ReadingLabels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_name: str | None = None
    invoice_number: str | None = None
    purchase_order_number: str | None = None
    issued_on: date | None = None
    currency: str | None = None
    lines: list[ReadingLineLabels] | None = Field(default=None, min_length=1)
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None


@dataclass(frozen=True)
class ReadingCase:
    case_id: str
    document: InvoiceFile
    expected: ReadingLabels


class Accuracy(BaseModel):
    correct: int = 0
    total: int = 0

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.total if self.total else None

    @model_serializer
    def serialize(self) -> dict[str, int | float | None]:
        return {
            "correct": self.correct,
            "total": self.total,
            "accuracy": self.accuracy,
        }


class InvoiceAccuracy(BaseModel):
    case_id: str
    invoice_id: UUID
    expected: ReadingLabels
    actual: InvoiceFields | None
    errors: list[str]


class ReadingReport(BaseModel):
    evaluated_at: datetime
    sample_version: str
    sample_sha256: str | None = None
    sample_source: dict[str, JsonValue] | None = None
    scoring_version: str = "reading-fields-v1"
    model: str
    per_field: dict[str, Accuracy]
    overall: Accuracy
    invoices: list[InvoiceAccuracy]


class SampleFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    filename: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(jpg|png|pdf)$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected: ReadingLabels


class SampleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    source: dict[str, JsonValue]
    cases: list[SampleFile] = Field(min_length=1)


@dataclass(frozen=True)
class ReadingSample:
    version: str
    sha256: str
    source: dict[str, JsonValue]
    cases: list[ReadingCase]


class FakeReadingFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    responses: dict[str, InvoiceFields | None]
    expected_per_field: dict[str, Accuracy]
    expected_overall: Accuracy


@dataclass(frozen=True)
class SampleInvoiceReader:
    responses: dict[str, InvoiceFields | None]

    @property
    def uses_live_model(self) -> bool:
        return False

    def read(self, document: InvoiceFile) -> InvoiceFields | None:
        return self.responses[document.filename]


def load_reading_sample(directory: Path = DEFAULT_SAMPLE) -> ReadingSample:
    manifest_bytes = (directory / "manifest.json").read_bytes()
    manifest = SampleManifest.model_validate_json(manifest_bytes)
    if len({case.case_id for case in manifest.cases}) != len(manifest.cases):
        raise ValueError("Reading sample case IDs must be unique.")
    if len({case.filename for case in manifest.cases}) != len(manifest.cases):
        raise ValueError("Reading sample filenames must be unique.")
    content_types = {
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".pdf": "application/pdf",
    }
    cases: list[ReadingCase] = []
    for case in manifest.cases:
        content = (directory / case.filename).read_bytes()
        if sha256(content).hexdigest() != case.sha256:
            raise ValueError(f"Reading sample checksum mismatch: {case.filename}")
        cases.append(
            ReadingCase(
                case_id=case.case_id,
                document=InvoiceFile(
                    filename=case.filename,
                    content_type=content_types[Path(case.filename).suffix],
                    content=content,
                ),
                expected=case.expected,
            )
        )
    return ReadingSample(
        version=manifest.version,
        sha256=sha256(manifest_bytes).hexdigest(),
        source=manifest.source,
        cases=cases,
    )


def evaluate_reading(
    processing: InvoiceProcessing,
    company_id: UUID,
    cases: list[ReadingCase],
    *,
    sample_version: str,
    model: str,
) -> ReadingReport:
    if not cases:
        raise ValueError("The reading sample must contain at least one Invoice.")
    scores: dict[str, Accuracy] = {}
    invoices: list[InvoiceAccuracy] = []

    def record(
        field: str,
        expected: object,
        actual: object,
        path: str,
        errors: list[str],
    ) -> None:
        score = scores.setdefault(field, Accuracy())
        score.total += 1
        if expected == actual:
            score.correct += 1
        else:
            errors.append(path)

    for case in cases:
        uploaded = processing.upload(company_id, case.document)
        result = processing.process(company_id, uploaded.id)
        errors: list[str] = []

        expected_values: dict[str, object] = case.expected.model_dump()
        actual_values: dict[str, object] = (
            result.fields.model_dump() if result.fields else {}
        )
        for field, expected in expected_values.items():
            if field != "lines" and expected is not None:
                record(field, expected, actual_values.get(field), field, errors)

        expected_lines = case.expected.lines or []
        actual_lines = result.fields.lines if result.fields and expected_lines else []
        labelled_line_fields = {
            field
            for line in expected_lines
            for field, value in line.model_dump().items()
            if value is not None
        }
        for position in range(max(len(expected_lines), len(actual_lines))):
            expected_line: dict[str, object] = (
                expected_lines[position].model_dump()
                if position < len(expected_lines)
                else {}
            )
            actual_line: dict[str, object] = (
                actual_lines[position].model_dump()
                if position < len(actual_lines)
                else {}
            )
            for field in ReadingLineLabels.model_fields:
                if field not in labelled_line_fields:
                    continue
                expected = expected_line.get(field)
                if position < len(expected_lines) and expected is None:
                    continue
                record(
                    f"lines.{field}",
                    expected,
                    actual_line.get(field),
                    f"lines.{position}.{field}",
                    errors,
                )
        invoices.append(
            InvoiceAccuracy(
                case_id=case.case_id,
                invoice_id=result.id,
                expected=case.expected,
                actual=result.fields,
                errors=errors,
            )
        )
    return ReadingReport(
        evaluated_at=datetime.now(UTC),
        sample_version=sample_version,
        model=model,
        per_field=scores,
        overall=Accuracy(
            correct=sum(score.correct for score in scores.values()),
            total=sum(score.total for score in scores.values()),
        ),
        invoices=invoices,
    )


def save_reading_report(report: ReadingReport, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = report.evaluated_at.strftime("%Y%m%dT%H%M%S%fZ")
    path = directory / f"reading-{timestamp}-{uuid4().hex}.json"
    with path.open("x", encoding="utf-8") as destination:
        destination.write(report.model_dump_json(indent=2) + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score labelled Invoice reading.")
    parser.add_argument("--sample-dir", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--output-dir", type=Path, default=Path("evals/results"))
    parser.add_argument("--check", action="store_true", help="Check the fake baseline.")
    arguments = parser.parse_args(argv)
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        parser.error("Set TEST_DATABASE_URL to a Postgres database with pgvector.")
    try:
        sample = load_reading_sample(arguments.sample_dir)
        fake = FakeReadingFixture.model_validate_json(
            (arguments.sample_dir / "fake.json").read_bytes()
        )
        if fake.responses.keys() != {case.document.filename for case in sample.cases}:
            raise ValueError("Fake responses must cover exactly the reading sample.")
        initialize_database(database_url)
        embeddings = ScriptedEmbeddings()
        erp_tools = ERPTools(database_url, embeddings)
        company = DemoCompanies(database_url, embeddings).start(None).company
        processing = InvoiceProcessing(
            database_url,
            reader=SampleInvoiceReader(fake.responses),
            erp_tools=erp_tools,
            daily_ai_limit=DailyAILimit(database_url),
        )
        report = evaluate_reading(
            processing,
            company.id,
            sample.cases,
            sample_version=sample.version,
            model=fake.model,
        )
        report.sample_sha256 = sample.sha256
        report.sample_source = sample.source
        path = save_reading_report(report, arguments.output_dir)
        for field, score in sorted(report.per_field.items()):
            print(f"{field}: {score.correct}/{score.total} ({score.accuracy or 0:.2%})")
        print(
            f"Overall: {report.overall.correct}/{report.overall.total} "
            f"({report.overall.accuracy or 0:.2%})"
        )
        print(f"Saved: {path}")
        if arguments.check and (
            report.per_field != fake.expected_per_field
            or report.overall != fake.expected_overall
        ):
            print(
                "Fake reading scores do not match the saved baseline.", file=sys.stderr
            )
            return 1
        return 0
    except (OSError, ValueError) as error:
        print(f"Reading evaluation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
