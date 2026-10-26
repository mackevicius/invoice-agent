import os
from pathlib import Path

from invoice_agent.clients.invoice_reader import InvoiceReader, ScriptedInvoiceReader
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
    if provider == "openai":
        return VisionInvoiceReader(
            provider="openai", model=os.environ.get("INVOICE_MODEL") or "gpt-4.1-mini"
        )
    if provider == "anthropic":
        return VisionInvoiceReader(
            provider="anthropic",
            model=os.environ.get("INVOICE_MODEL") or "claude-haiku-4-5-20251001",
        )
    raise ValueError("INVOICE_MODEL_PROVIDER must be openai, anthropic, or fake.")
