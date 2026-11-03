import argparse
import os
from dataclasses import dataclass
from typing import Literal

from invoice_agent.clients.embeddings import LocalEmbeddings
from invoice_agent.clients.line_pairing import ModelLinePairer
from invoice_agent.clients.tracing import RunTracing, configured_tracing
from invoice_agent.clients.vision_reader import VisionInvoiceReader


def evaluation_arguments(
    parser: argparse.ArgumentParser, argv: list[str] | None
) -> argparse.Namespace:
    parser.add_argument("--check", action="store_true", help="Check the fake baseline.")
    parser.add_argument(
        "--provider", choices=["fake", "openai", "anthropic"], default="fake"
    )
    parser.add_argument("--model", help="Override the live provider's model.")
    arguments = parser.parse_args(argv)
    if arguments.provider != "fake" and arguments.check:
        parser.error("--check is only available for the fake baseline.")
    if arguments.provider == "fake" and arguments.model:
        parser.error("--model requires a live provider.")
    return arguments


@dataclass(frozen=True)
class LiveEvaluation:
    provider: Literal["openai", "anthropic"]
    model: str
    embeddings: LocalEmbeddings
    reader: VisionInvoiceReader
    line_pairer: ModelLinePairer
    tracing: RunTracing


def live_evaluation(
    provider: Literal["openai", "anthropic"], model: str | None
) -> LiveEvaluation:
    key = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    if not os.environ.get(key, "").strip():
        raise ValueError(f"Set {key} for live evaluations.")
    tracing = configured_tracing()
    if tracing.client is None:
        raise ValueError("Live evaluations require enabled Langfuse with both keys.")
    model = (
        model
        or os.environ.get("INVOICE_MODEL")
        or ("gpt-4.1-mini" if provider == "openai" else "claude-haiku-4-5-20251001")
    )
    return LiveEvaluation(
        provider=provider,
        model=model,
        embeddings=LocalEmbeddings(),
        reader=VisionInvoiceReader(provider=provider, model=model),
        line_pairer=ModelLinePairer(provider=provider, model=model),
        tracing=tracing,
    )
