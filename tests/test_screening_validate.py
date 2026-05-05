"""Regression tests for Agent 1 screening validation (inclusion / tiers).

Covers the cases you care about for manual verification:
- unrelated → dropped
- 0/5 → dropped
- 2/5 → dropped
- 4/5 → kept as recommended (passes_filter True)

Run: pytest tests/test_screening_validate.py -v
"""

from app.agents.agent1 import TenderExtractionAgent


def _item(step1: dict, unrelated: bool = False, url: str = "https://example.com/o"):
    return {
        "title": "Test opportunity",
        "url": url,
        "description": "d",
        "screening": {
            "unrelated_to_precise_scope": unrelated,
            "step1": step1,
            "step2": {},
            "step3": {},
        },
    }


def test_validate_preserves_optional_source_language_lowercased_and_capped():
    agent = TenderExtractionAgent()
    step1 = {
        "mission_alignment": True,
        "sector_relevance": True,
        "activity_fit": True,
        "geographic_fit": True,
        "eligibility_quick_check": False,
    }
    raw = _item(step1, url="https://example.com/with-lang")
    raw["screening"]["source_language"] = " FR "
    out = agent._validate([raw])
    assert len(out) == 1
    assert out[0]["screening"]["source_language"] == "fr"


def test_validate_drops_blank_source_language():
    agent = TenderExtractionAgent()
    step1 = {k: True for k in agent.STEP1_KEYS}
    raw = _item(step1, url="https://example.com/no-lang")
    raw["screening"]["source_language"] = "   "
    out = agent._validate([raw])
    assert "source_language" not in out[0]["screening"]


def test_screening_prompt_declares_multilingual_handling():
    from app.agents.screening_prompt import PRECISE_SCREENING_CHECKLIST_MARKDOWN

    low = PRECISE_SCREENING_CHECKLIST_MARKDOWN.lower()
    assert low.count("multilingual sources") >= 1
    assert "output in english only" in low


def test_unrelated_dropped_even_if_step1_all_yes():
    """Unrelated noise: excluded regardless of Step 1 booleans."""
    agent = TenderExtractionAgent()
    step1 = {k: True for k in agent.STEP1_KEYS}
    out = agent._validate([_item(step1, unrelated=True)])
    assert out == []


def test_zero_of_five_dropped():
    """0/5 YES → not persisted."""
    agent = TenderExtractionAgent()
    step1 = {k: False for k in agent.STEP1_KEYS}
    out = agent._validate([_item(step1, url="https://example.com/0of5")])
    assert out == []


def test_two_of_five_dropped_as_not_relevant_enough():
    """2/5 YES → dropped under the stricter initial filtering checklist."""
    agent = TenderExtractionAgent()
    step1 = {
        "mission_alignment": True,
        "sector_relevance": True,
        "activity_fit": False,
        "geographic_fit": False,
        "eligibility_quick_check": False,
    }
    out = agent._validate([_item(step1, url="https://example.com/2of5")])
    assert out == []


def test_four_of_five_kept_recommended():
    """4/5 YES → recommended tier; passes_filter True (green-style row + Agent 2 queue)."""
    agent = TenderExtractionAgent()
    step1 = {
        "mission_alignment": True,
        "sector_relevance": True,
        "activity_fit": True,
        "geographic_fit": True,
        "eligibility_quick_check": False,
    }
    out = agent._validate([_item(step1, url="https://example.com/4of5")])
    assert len(out) == 1
    assert out[0]["screening"]["yes_count"] == 4
    assert out[0]["screening"]["passes_filter"] is True


def test_three_of_five_boundary_recommended():
    """≥3 YES → passes_filter True (boundary check)."""
    agent = TenderExtractionAgent()
    step1 = {
        "mission_alignment": True,
        "sector_relevance": True,
        "activity_fit": True,
        "geographic_fit": False,
        "eligibility_quick_check": False,
    }
    out = agent._validate([_item(step1, url="https://example.com/3of5")])
    assert out[0]["screening"]["yes_count"] == 3
    assert out[0]["screening"]["passes_filter"] is True


def test_batch_unrelated_zero_two_four_only_strong_survives():
    """One validate call: unrelated + 0/5 + 2/5 + 4/5 → keep only recommended."""
    agent = TenderExtractionAgent()
    batch = [
        _item({k: True for k in agent.STEP1_KEYS}, unrelated=True, url="https://example.com/u"),
        _item({k: False for k in agent.STEP1_KEYS}, url="https://example.com/z"),
        _item(
            {
                "mission_alignment": True,
                "sector_relevance": True,
                "activity_fit": False,
                "geographic_fit": False,
                "eligibility_quick_check": False,
            },
            url="https://example.com/two",
        ),
        _item(
            {
                "mission_alignment": True,
                "sector_relevance": True,
                "activity_fit": True,
                "geographic_fit": True,
                "eligibility_quick_check": False,
            },
            url="https://example.com/four",
        ),
    ]
    out = agent._validate(batch)
    assert len(out) == 1
    tiers = {(x["screening"]["yes_count"], x["screening"]["passes_filter"]) for x in out}
    assert tiers == {(4, True)}


def test_parse_json_strips_qwen_style_thinking_then_bracket_extracts():
    """Simulates local-model output: reasoning XML then prose then JSON array."""
    agent = TenderExtractionAgent()
    inner = (
        '[{"title":"T","url":"https://u.example/x","description":"","screening":'
        '{"unrelated_to_precise_scope":false,"step1":{"mission_alignment":true,'
        '"sector_relevance":false,"activity_fit":false,"geographic_fit":false,'
        '"eligibility_quick_check":false}}}]'
    )
    raw = (
        "<thinking>\nconsider steps\n</thinking>\n"
        "Below is the JSON you requested:\n"
        + inner
        + "\ntrailing junk"
    )
    out = agent._parse_json(raw)
    assert len(out) == 1
    assert out[0]["title"] == "T"


def test_parse_json_fenced_inside_prose():
    agent = TenderExtractionAgent()
    raw = 'Analysis complete.\n```json\n[{"title":"X","url":"https://x","description":"","screening":{"unrelated_to_precise_scope":false,"step1":{"mission_alignment":true,"sector_relevance":true,"activity_fit":true,"geographic_fit":false,"eligibility_quick_check":false}}}]\n```'
    out = agent._parse_json(raw)
    assert len(out) == 1
    assert out[0]["title"] == "X"


def test_parse_json_single_object_root_ollama_json_mode():
    """Ollama format=json often emits one object instead of a one-element array."""
    agent = TenderExtractionAgent()
    raw = (
        '{"title":"T","url":"https://u.example/x","description":"",'
        '"screening":{"unrelated_to_precise_scope":false,'
        '"step1":{"mission_alignment":true,"sector_relevance":true,"activity_fit":true,'
        '"geographic_fit":true,"eligibility_quick_check":true}}}'
    )
    out = agent._parse_json(raw)
    assert len(out) == 1
    assert out[0]["title"] == "T"


def test_parse_json_object_root_with_nested_arrays_not_misread_as_root_array():
    """First ``[``/last ``]`` must not hijack a root object that contains list fields."""
    agent = TenderExtractionAgent()
    raw = (
        '{"title":"T","url":"https://u.example/x","description":"",'
        '"screening":{"step2":{"opportunity_characteristics":["a","b"],'
        '"strategic_signals":[]},"unrelated_to_precise_scope":false,'
        '"step1":{"mission_alignment":true,"sector_relevance":false,"activity_fit":false,'
        '"geographic_fit":false,"eligibility_quick_check":false}}}'
    )
    out = agent._parse_json(raw)
    assert len(out) == 1
    assert out[0]["title"] == "T"


def test_parse_json_when_array_inside_qwen_redacted_thinking_block():
    """Qwen 3.x sometimes puts the JSON array inside the reasoning wrapper — strip-first used to delete it."""
    agent = TenderExtractionAgent()
    inner = (
        '[{"title":"T","url":"https://u.example/x","description":"","screening":'
        '{"unrelated_to_precise_scope":false,"step1":{"mission_alignment":true,'
        '"sector_relevance":false,"activity_fit":false,"geographic_fit":false,'
        '"eligibility_quick_check":false}}}]'
    )
    open_tag = "<" + "redacted_thinking" + ">"
    close_tag = "</" + "redacted_thinking" + ">"
    raw = open_tag + inner + close_tag
    out = agent._parse_json(raw)
    assert len(out) == 1
    assert out[0]["title"] == "T"
