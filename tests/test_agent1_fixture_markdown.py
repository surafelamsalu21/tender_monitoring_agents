"""Agent 1 markdown fixtures under tests/fixtures/agent1_screening/."""

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "agent1_screening"
FIXTURES = (
    "zero_match_notice.md",
    "low_match_notice.md",
    "strong_match_notice.md",
    "strong_match_notice_fr.md",
)


def _require_live_llm_backend() -> None:
    """Integration tests call the real Chat model from `get_chat_llm` (matches app/agents/agent1.py)."""
    from app.core.config import settings

    provider = (settings.LLM_PROVIDER or "openai").lower().strip()
    if provider == "openai":
        key = (settings.OPENAI_API_KEY or "").strip()
        if not key:
            pytest.skip(
                "LLM_PROVIDER=openai requires OPENAI_API_KEY (or switch to LLM_PROVIDER=ollama for local Qwen)."
            )
    elif provider == "ollama":
        return  # assumes `ollama serve` and pulled model — no cloud key needed
    else:
        pytest.skip(f"Unsupported LLM_PROVIDER '{settings.LLM_PROVIDER}' for Agent 1 integration tests")


def test_agent1_screening_fixtures_exist_and_non_empty():
    for name in FIXTURES:
        path = FIXTURE_DIR / name
        assert path.is_file(), f"Missing fixture: {path}"
        text = path.read_text(encoding="utf-8")
        assert len(text.strip()) > 80, f"Fixture too short: {name}"


@pytest.mark.integration
def test_agent1_llm_on_fixture_strong_match_prefers_recommended_tier():
    """Uses configured LLM (OpenAI or Ollama). Strong fixture should usually yield ≥3 YES."""
    _require_live_llm_backend()

    import asyncio

    from app.agents.agent1 import TenderExtractionAgent

    content = (FIXTURE_DIR / "strong_match_notice.md").read_text(encoding="utf-8")
    agent = TenderExtractionAgent()
    items = asyncio.run(agent.extract_and_screen_opportunities(page_content=content))

    assert len(items) >= 1, "Expected at least one opportunity from strong_match_notice.md"
    assert any(
        bool((it.get("screening") or {}).get("passes_filter")) for it in items
    ), "Expected at least one recommended-tier row (passes_filter True)"


@pytest.mark.integration
def test_agent1_llm_on_fixture_low_match_often_not_recommended():
    """Low-match fixture should usually stay visible but not passes_filter when kept."""
    _require_live_llm_backend()

    import asyncio

    from app.agents.agent1 import TenderExtractionAgent

    content = (FIXTURE_DIR / "low_match_notice.md").read_text(encoding="utf-8")
    agent = TenderExtractionAgent()
    items = asyncio.run(agent.extract_and_screen_opportunities(page_content=content))

    if not items:
        pytest.skip("Model returned no rows for low_match fixture — rerun or relax fixture")

    assert not any(
        bool((it.get("screening") or {}).get("passes_filter")) for it in items
    ), "Expected low_match_notice.md to produce no recommended-tier rows"


@pytest.mark.integration
def test_agent1_llm_on_fixture_zero_match_often_empty():
    """Zero-tier notice should often produce no kept rows after validation."""
    _require_live_llm_backend()

    import asyncio

    from app.agents.agent1 import TenderExtractionAgent

    content = (FIXTURE_DIR / "zero_match_notice.md").read_text(encoding="utf-8")
    agent = TenderExtractionAgent()
    items = asyncio.run(agent.extract_and_screen_opportunities(page_content=content))

    assert len(items) == 0, (
        "Expected zero_match_notice.md to yield no post-validation opportunities; "
        "if this fails, tighten the fixture text or accept model variance."
    )


@pytest.mark.integration
def test_agent1_llm_on_french_strong_fixture_english_summaries_and_tier():
    """French markdown same semantics as strong_match; expect recommended tier + English blobs."""
    _require_live_llm_backend()

    import asyncio

    from app.agents.agent1 import TenderExtractionAgent

    content = (FIXTURE_DIR / "strong_match_notice_fr.md").read_text(encoding="utf-8")
    agent = TenderExtractionAgent()
    items = asyncio.run(agent.extract_and_screen_opportunities(page_content=content))

    assert len(items) >= 1, "Expected at least one opportunity from French strong fixture"

    tiers = [
        it
        for it in items
        if bool((it.get("screening") or {}).get("passes_filter"))
    ]
    assert tiers, "French fixture should mirror strong-tier geography/sector scoring"

    for it in tiers:
        blob = f"{it.get('title','')} {it.get('description','')}".lower()
        assert "manifestation d'intérêt" not in blob and "manifestation d&#39;intérêt" not in blob
        assert "éthiopie" not in blob
        geography_ok = (
            "ethiopia" in blob
            or "eastern africa" in blob
            or "east africa" in blob
            or "east african" in blob
            or "msme" in blob
            or "productive use" in blob
            or ("energy" in blob and ("enterprise" in blob or "consulting" in blob))
        )
        assert geography_ok, (
            "English summary should mention geography or core theme "
            "(Ethiopia / East Africa / productive use of energy / MSMEs)."
        )
