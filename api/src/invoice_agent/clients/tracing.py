import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langfuse import Langfuse, LangfuseSpan, propagate_attributes
from langfuse.langchain import CallbackHandler

from invoice_agent.schemas.invoices import InvoiceDetail

logger = logging.getLogger(__name__)


@dataclass
class RunTrace:
    url: str | None = None
    callbacks: list[BaseCallbackHandler] = field(default_factory=list)
    observation: LangfuseSpan | None = None

    def complete(self, invoice: InvoiceDetail) -> None:
        if self.observation is not None:
            self.observation.update(output=invoice.model_dump(mode="json"))


class RunTracing:
    def __init__(
        self, client: Langfuse | None = None, *, public_key: str | None = None
    ) -> None:
        self.client = client
        self.public_key = public_key

    @contextmanager
    def run(self, company_id: UUID, invoice_id: UUID) -> Iterator[RunTrace]:
        if self.client is None:
            yield RunTrace()
            return
        with self.client.start_as_current_observation(
            as_type="span",
            name="Invoice run",
            trace_context={"trace_id": Langfuse.create_trace_id()},
            input={"company_id": str(company_id), "invoice_id": str(invoice_id)},
        ) as observation:
            with propagate_attributes(
                trace_name="Invoice run",
                session_id=str(company_id),
                metadata={"invoice_id": str(invoice_id)},
            ):
                yield RunTrace(
                    url=self._trace_url(observation.trace_id),
                    callbacks=[CallbackHandler(public_key=self.public_key)],
                    observation=observation,
                )

    def _trace_url(self, trace_id: str) -> str | None:
        if self.client is None:
            return None
        try:
            return self.client.get_trace_url(trace_id=trace_id)
        except Exception:
            logger.exception("Langfuse trace link is unavailable.")
            return None

    def tool[ToolResult, **ToolParameters](
        self,
        name: str,
        operation: Callable[ToolParameters, ToolResult],
        *args: ToolParameters.args,
        **kwargs: ToolParameters.kwargs,
    ) -> ToolResult:
        if self.client is None:
            return operation(*args, **kwargs)
        with self.client.start_as_current_observation(
            as_type="tool", name=name, input={"args": args, "kwargs": kwargs}
        ) as observation:
            result = operation(*args, **kwargs)
            observation.update(output=result)
        return result

    def close(self) -> None:
        if self.client is not None:
            try:
                self.client.shutdown()
            except Exception:
                logger.exception("Langfuse shutdown failed.")


def configured_tracing() -> RunTracing:
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    enabled = os.environ.get("LANGFUSE_TRACING_ENABLED", "true").lower()
    if not public_key or not secret_key or enabled in {"false", "0", "off"}:
        return RunTracing()
    try:
        return RunTracing(
            Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                base_url=os.environ.get("LANGFUSE_BASE_URL") or None,
                sample_rate=1.0,
            ),
            public_key=public_key,
        )
    except Exception:
        logger.exception("Langfuse tracing is unavailable.")
        return RunTracing()
