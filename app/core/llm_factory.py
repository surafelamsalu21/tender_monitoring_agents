"""
LLM factory for selecting OpenAI, Anthropic, Gemini, Groq, or Ollama providers.
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
    provider = (settings.LLM_PROVIDER or "anthropic").lower().strip()
    if provider == "claude":
        provider = "anthropic"

    if provider == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY (or CLAUDE_API_KEY) is required when "
                "LLM_PROVIDER=anthropic."
            )
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=settings.ANTHROPIC_MODEL,
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=temperature,
            timeout=settings.LLM_REQUEST_TIMEOUT_SEC,
            max_retries=settings.LLM_MAX_RETRIES,
        )

    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY is required when LLM_PROVIDER=openai."
            )
        return ChatOpenAI(
            model=settings.OPENAI_MODEL,
            api_key=settings.OPENAI_API_KEY,
            temperature=temperature,
            timeout=settings.LLM_REQUEST_TIMEOUT_SEC,
            max_retries=settings.LLM_MAX_RETRIES,
        )

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

    if provider == "gemini":
        if not settings.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY is required when LLM_PROVIDER=gemini. "
                "Get a free key at https://aistudio.google.com"
            )
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=temperature,
        )

    if provider == "groq":
        if not settings.GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY is required when LLM_PROVIDER=groq. "
                "Get a free key at https://console.groq.com"
            )
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=settings.GROQ_MODEL,
            api_key=settings.GROQ_API_KEY,
            temperature=temperature,
        )

    raise ValueError(
        f"Unsupported LLM_PROVIDER '{settings.LLM_PROVIDER}'. "
        "Use 'anthropic', 'openai', 'gemini', 'groq', or 'ollama'."
    )
