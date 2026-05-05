"""
LLM factory for selecting OpenAI or Ollama providers.
"""
from typing import Any, Optional

from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama

from app.core.config import settings


def get_chat_llm(temperature: float = 0.1, *, ollama_format: Optional[str] = None):
    """Return a chat model instance based on configured provider.

    ``ollama_format``: when set, overrides ``OLLAMA_FORMAT`` for this instance only.
    Use ``\"none\"`` to omit ``format=`` (often better for tiny models on free-text JSON).
    """
    provider = (settings.LLM_PROVIDER or "openai").lower().strip()

    if provider == "ollama":
        kwargs: dict[str, Any] = {
            "model": settings.OLLAMA_MODEL,
            "base_url": settings.OLLAMA_BASE_URL,
            "temperature": temperature,
        }
        fmt_source = settings.OLLAMA_FORMAT if ollama_format is None else ollama_format
        fmt = (fmt_source or "").strip()
        if fmt.lower() not in ("", "none", "off", "false", "0"):
            kwargs["format"] = fmt
        http_timeout = getattr(settings, "OLLAMA_HTTP_TIMEOUT_SEC", None)
        if http_timeout is not None and float(http_timeout) > 0:
            kwargs["async_client_kwargs"] = {"timeout": float(http_timeout)}
        return ChatOllama(**kwargs)

    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY is required when LLM_PROVIDER=openai."
            )
        return ChatOpenAI(
            model=settings.OPENAI_MODEL,
            api_key=settings.OPENAI_API_KEY,
            temperature=temperature,
        )

    raise ValueError(
        f"Unsupported LLM_PROVIDER '{settings.LLM_PROVIDER}'. Use 'openai' or 'ollama'."
    )
