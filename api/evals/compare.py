import argparse
import sys
from pathlib import Path

from pydantic import RootModel

from evals.decisions import DecisionReport
from evals.reading import ReadingReport

type Report = ReadingReport | DecisionReport


def _accuracy(report: Report) -> str:
    if isinstance(report, ReadingReport):
        accuracy = report.overall.accuracy
        correct, total = report.overall.correct, report.overall.total
    else:
        accuracy = report.accuracy
        correct, total = report.correct, report.total
    if accuracy is None:
        return "unavailable"
    return f"{accuracy:.2%} ({correct}/{total})"


def _row(cells: list[str]) -> str:
    return (
        "| "
        + " | ".join(cell.replace("|", "\\|").replace("\n", " ") for cell in cells)
        + " |"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare saved Invoice eval reports.")
    parser.add_argument("reports", nargs="+", type=Path)
    arguments = parser.parse_args(argv)
    groups: dict[tuple[str, str, str | None, str], list[tuple[Path, Report]]] = {}
    try:
        paths: list[Path] = []
        for source in arguments.reports:
            paths.extend(sorted(source.glob("*.json")) if source.is_dir() else [source])
        if not paths:
            raise ValueError("No evaluation reports were found.")
        for path in paths:
            report = (
                RootModel[ReadingReport | DecisionReport]
                .model_validate_json(path.read_bytes())
                .root
            )
            kind = "Reading" if isinstance(report, ReadingReport) else "Decisions"
            key = (
                kind,
                report.sample_version,
                report.sample_sha256,
                report.scoring_version,
            )
            groups.setdefault(key, []).append((path, report))
    except (OSError, ValueError) as error:
        print(f"Report comparison failed: {error}", file=sys.stderr)
        return 1
    for (kind, version, checksum, scoring), entries in groups.items():
        print(f"## {kind}: {version}")
        print(f"Scoring: {scoring}; SHA256: {checksum or 'unavailable'}\n")
        print(
            _row(
                ["Metric"]
                + [
                    f"{report.provider}/{report.model} "
                    f"({report.evaluated_at.isoformat()}; {path.name})"
                    for path, report in entries
                ]
            )
        )
        print(_row(["---"] + ["---:"] * len(entries)))
        print(_row(["Accuracy"] + [_accuracy(report) for _, report in entries]))
        print(
            _row(
                ["Wrong Auto-Approvals"]
                + [
                    str(report.wrong_auto_approvals)
                    if isinstance(report, DecisionReport)
                    else "n/a"
                    for _, report in entries
                ]
            )
        )
        print(
            _row(
                ["Average cost / Invoice (USD)"]
                + [
                    f"${report.average_cost_usd:.6f}"
                    if report.average_cost_usd is not None
                    else "unavailable"
                    for _, report in entries
                ]
            )
        )
        print(
            _row(
                ["Average time / Invoice"]
                + [
                    f"{report.average_time_seconds:.3f} s"
                    if report.average_time_seconds is not None
                    else "unavailable"
                    for _, report in entries
                ]
            )
        )
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
