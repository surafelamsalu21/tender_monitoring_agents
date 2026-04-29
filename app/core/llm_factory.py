"""
LLM factory for selecting OpenAI or Ollama providers.
"""
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama

from app.core.config import settings


def get_chat_llm(temperature: float = 0.1):
    """Return a chat model instance based on configured provider."""
    provider = (settings.LLM_PROVIDER or "openai").lower().strip()

    if provider == "ollama":
        return ChatOllama(
            model=settings.OLLAMA_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=temperature,
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
        )

    raise ValueError(
        f"Unsupported LLM_PROVIDER '{settings.LLM_PROVIDER}'. Use 'openai' or 'ollama'."
    )
