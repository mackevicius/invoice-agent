import os
from typing import Literal

from langchain_core.language_models import BaseChatModel


def configured_live_model() -> tuple[Literal["openai", "anthropic"], str]:
    provider = os.environ.get("INVOICE_MODEL_PROVIDER", "openai").lower()
    model = os.environ.get("INVOICE_MODEL")
    if provider == "openai":
        return "openai", model or "gpt-4.1-mini"
    if provider == "anthropic":
        return "anthropic", model or "claude-haiku-4-5-20251001"
    raise ValueError("INVOICE_MODEL_PROVIDER must be openai, anthropic, or fake.")


def create_chat_model(
    provider: Literal["openai", "anthropic"], model: str, *, max_tokens: int
) -> BaseChatModel:
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model, timeout=45, max_retries=0, max_completion_tokens=max_tokens
        )
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model_name=model,
        timeout=45,
        max_retries=0,
        max_tokens_to_sample=max_tokens,
        stop=None,
    )
