import os
from pathlib import Path

from pydantic import TypeAdapter

from invoice_agent.clients.chat_model import configured_live_model
from invoice_agent.clients.embeddings import (
    LocalEmbeddings,
    ScriptedEmbeddings,
    TextEmbeddings,
)
from invoice_agent.clients.invoice_reader import InvoiceReader, ScriptedInvoiceReader
from invoice_agent.clients.line_pairing import (
    LinePairer,
    ModelLinePairer,
    ScriptedLinePairer,
)
from invoice_agent.clients.vision_reader import VisionInvoiceReader
from invoice_agent.schemas.invoice_fields import InvoiceReadResult


def configured_reader() -> InvoiceReader:
    provider = os.environ.get("INVOICE_MODEL_PROVIDER", "openai").lower()
    if provider == "fake":
        response_path = os.environ.get("INVOICE_FAKE_RESPONSE")
        fields = (
            InvoiceReadResult.model_validate_json(
                Path(response_path).read_text(encoding="utf-8")
            ).invoice
            if response_path
            else None
        )
        return ScriptedInvoiceReader(fields)
    live_provider, model = configured_live_model()
    return VisionInvoiceReader(provider=live_provider, model=model)


def configured_embeddings() -> TextEmbeddings:
    if os.environ.get("INVOICE_MODEL_PROVIDER", "openai").lower() == "fake":
        return ScriptedEmbeddings()
    return LocalEmbeddings()


def configured_line_pairer() -> LinePairer:
    provider = os.environ.get("INVOICE_MODEL_PROVIDER", "openai").lower()
    if provider == "fake":
        choices = TypeAdapter(dict[str, str | None]).validate_json(
            os.environ.get("INVOICE_FAKE_LINE_CHOICES") or "{}"
        )
        return ScriptedLinePairer(choices)
    live_provider, model = configured_live_model()
    return ModelLinePairer(provider=live_provider, model=model)
