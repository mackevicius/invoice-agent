from collections.abc import Sequence
from datetime import datetime
from time import monotonic, sleep
from typing import Literal
from uuid import UUID

from langchain_core.tracers.context import collect_runs
from pydantic import BaseModel

from invoice_agent.clients.tracing import RunTracing
from invoice_agent.schemas.invoices import InvoiceDetail
from invoice_agent.services.invoice_processing import InvoiceProcessing


class EvaluationReport(BaseModel):
    evaluated_at: datetime
    sample_version: str
    sample_sha256: str | None = None
    scoring_version: str
    provider: Literal["fake", "openai", "anthropic"] = "fake"
    model: str
    average_cost_usd: float | None = None
    average_time_seconds: float | None = None

    def require_measurements(self) -> None:
        if self.provider != "fake" and (
            self.average_cost_usd is None or self.average_time_seconds is None
        ):
            raise ValueError(
                "Langfuse measurements are incomplete; see Invoice metrics_error."
            )


class InvoiceMetrics(BaseModel):
    trace_url: str | None = None
    cost_usd: float | None = None
    time_seconds: float | None = None
    metrics_error: str | None = None
    generation_count: int = 0


def process_for_report(
    processing: InvoiceProcessing, company_id: UUID, invoice_id: UUID
) -> tuple[InvoiceDetail, int]:
    with collect_runs() as recorder:
        result = processing.process(company_id, invoice_id)
    pending = list(recorder.traced_runs)
    generation_count = 0
    while pending:
        run = pending.pop()
        generation_count += run.run_type == "llm"
        pending.extend(run.child_runs)
    return result, generation_count


def collect_metrics(invoices: Sequence[InvoiceMetrics], tracing: RunTracing) -> None:
    client = tracing.client
    if client is None:
        return
    client.flush()
    for invoice in invoices:
        if invoice.trace_url is None:
            invoice.metrics_error = "Langfuse trace URL is unavailable."
            continue
        deadline = monotonic() + 60
        delay = 0.5
        while True:
            try:
                page = client.api.observations.get_many(
                    trace_id=invoice.trace_url.rsplit("/", 1)[-1],
                    fields="core,basic,usage",
                    limit=1000,
                    request_options={"max_retries": 0, "timeout_in_seconds": 5},
                )
                observations = list(page.data)
                while page.meta.cursor:
                    page = client.api.observations.get_many(
                        trace_id=invoice.trace_url.rsplit("/", 1)[-1],
                        fields="core,basic,usage",
                        limit=1000,
                        cursor=page.meta.cursor,
                        request_options={"max_retries": 0, "timeout_in_seconds": 5},
                    )
                    observations.extend(page.data)
                root = next(
                    (
                        observation
                        for observation in observations
                        if observation.name == "Invoice run"
                        and observation.parent_observation_id is None
                    ),
                    None,
                )
                if root is None or root.end_time is None:
                    invoice.metrics_error = "Langfuse Invoice run is not available yet."
                else:
                    invoice.time_seconds = (
                        root.end_time - root.start_time
                    ).total_seconds()
                    generation_count = sum(
                        observation.type == "GENERATION" for observation in observations
                    )
                    costs = [
                        observation.total_cost
                        for observation in observations
                        if observation.type in {"GENERATION", "EMBEDDING"}
                    ]
                    if generation_count < invoice.generation_count:
                        invoice.metrics_error = (
                            "Langfuse model observations are incomplete."
                        )
                    elif any(cost is None for cost in costs):
                        invoice.metrics_error = (
                            "Langfuse cost is unavailable; check model pricing."
                        )
                    else:
                        invoice.cost_usd = sum(
                            cost for cost in costs if cost is not None
                        )
                        invoice.metrics_error = None
                        break
            except Exception as error:
                invoice.metrics_error = (
                    f"Langfuse metrics unavailable ({type(error).__name__})."
                )
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            sleep(min(delay, remaining))
            delay = min(delay * 2, 5)


def average(values: Sequence[float | None]) -> float | None:
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None) / len(values)
