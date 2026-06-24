"""
Deterministic geographic gate for Precise's East Africa / Ethiopia focus.

This is a POST-LLM hard filter.  The LLM sets ``geographic_fit`` based on the
screening prompt, but LLMs can make mistakes (e.g. passing Montenegro or Sri
Lanka tenders).  This module provides a rule-based safety net that runs AFTER
the LLM and can override an incorrect ``geographic_fit=true`` decision.

Allowed region: Ethiopia (priority) + East Africa
  Burundi, Comoros, Djibouti, Eritrea, Ethiopia, Kenya, Madagascar, Rwanda,
  Seychelles, Somalia, South Sudan, Sudan, Tanzania, Uganda
  + regional labels: East Africa, Horn of Africa, EAC, IGAD

Usage::

    from app.utils.geo_filter import is_geography_allowed

    allowed = is_geography_allowed(
        country=step3.get("country", ""),
        title=tender_title,
        description=tender_description,
    )
    # allowed=True  → clearly in region or ambiguous (let LLM stand)
    # allowed=False → clearly outside region → drop tender
"""
from __future__ import annotations

import logging
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical token sets (all lowercase)
# ---------------------------------------------------------------------------

# Tokens that POSITIVELY identify the work location as inside the allowed region.
# A single match is enough to accept.
_ALLOWED_TOKENS: frozenset[str] = frozenset({
    # Countries
    "ethiopia", "ethiopian",
    "kenya", "kenyan",
    "uganda", "ugandan",
    "tanzania", "tanzanian",
    "rwanda", "rwandan",
    "burundi", "burundian",
    "somalia", "somali", "somaliland",
    "djibouti",
    "eritrea", "eritrean",
    "south sudan",
    "sudan", "sudanese",
    "seychelles",
    "madagascar", "malagasy",
    "comoros", "comorian",
    # Regional labels
    "east africa", "east african",
    "horn of africa",
    "eac",   # East African Community
    "igad",  # Intergovernmental Authority on Development
    # Well-known capitals (unambiguous city → country mapping)
    "addis ababa",
    "nairobi",
    "kampala",
    "dar es salaam",
    "kigali",
    "mogadishu",
    "bujumbura",
    "juba",
    "asmara",
    "hargeisa",
})

# Tokens that DEFINITIVELY place the work OUTSIDE the allowed region.
# If found in the country field (or title, when country is empty), and NO
# allowed token is present, the tender is rejected.
_BLOCKED_TOKENS: frozenset[str] = frozenset({
    # Europe
    "montenegro", "albania", "serbia", "kosovo", "north macedonia", "macedonia",
    "brindisi", "italy", "france", "germany", "spain", "portugal", "greece",
    "united kingdom", "britain", "england", "scotland", "wales",
    "sweden", "norway", "denmark", "finland", "iceland",
    "poland", "ukraine", "romania", "bulgaria", "czech",
    "hungary", "austria", "switzerland", "belgium", "netherlands", "luxembourg",
    "turkey", "armenia", "azerbaijan", "georgia",  # Transcaucasia
    "russia", "belarus", "moldova", "latvia", "lithuania", "estonia",
    # Asia
    "sri lanka", "india", "pakistan", "bangladesh", "nepal", "bhutan",
    "myanmar", "thailand", "vietnam", "cambodia", "laos",
    "malaysia", "indonesia", "philippines", "singapore", "timor-leste",
    "china", "taiwan", "hong kong", "japan", "south korea", "north korea", "mongolia",
    "iran", "iraq", "syria", "lebanon", "israel", "palestine",
    "jordan", "yemen", "oman", "united arab emirates", "uae", "saudi arabia",
    "qatar", "kuwait", "bahrain",
    "kyrgyzstan", "tajikistan", "uzbekistan", "turkmenistan", "kazakhstan",
    "afghanistan",
    # Pacific
    "papua new guinea", "fiji", "samoa", "tonga", "vanuatu", "solomon islands",
    "australia", "new zealand",
    # Americas
    "brazil", "colombia", "peru", "chile", "argentina", "bolivia",
    "venezuela", "ecuador", "paraguay", "uruguay", "guyana", "suriname",
    "mexico", "guatemala", "honduras", "nicaragua", "el salvador",
    "costa rica", "panama", "belize",
    "haiti", "dominican republic", "cuba", "jamaica",
    "trinidad and tobago", "barbados", "bahamas",
    "united states", "u.s.a", "canada",
    # Non-EA Africa (must NOT overlap with allowed tokens above)
    "nigeria", "ghana", "senegal", "mali", "niger", "burkina faso",
    "guinea", "sierra leone", "liberia", "ivory coast", "cote d'ivoire",
    "togo", "benin", "cameroon", "gabon", "equatorial guinea",
    "democratic republic of congo", "republic of congo", "central african republic",
    "angola", "zambia", "zimbabwe", "malawi", "mozambique",
    "south africa", "namibia", "botswana", "lesotho", "eswatini", "swaziland",
    "egypt", "libya", "morocco", "algeria", "tunisia", "mauritania",
    "cape verde", "sao tome", "gambia", "mauritius",
    "chad",  # NOT in allowed list (different from Sudan)
})

# Country / geography strings that are ambiguous — do not reject based on these alone.
# The LLM's ``geographic_fit`` judgment stands.
_AMBIGUOUS_VALUES: frozenset[str] = frozenset({
    "", "unknown", "various", "multiple", "global", "worldwide",
    "tbd", "n/a", "na", "africa", "sub-saharan africa", "sub saharan africa",
    "developing countries", "developing world", "regional", "international",
    "multiple countries", "various countries",
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_geography_allowed(
    country: str,
    title: str = "",
    description: str = "",
) -> bool:
    """
    Post-LLM hard geographic gate.

    Returns ``True``  → geography is in the allowed East Africa/Ethiopia region,
                         OR it is ambiguous enough to let the LLM decision stand.
    Returns ``False`` → geography is clearly outside the allowed region; drop.

    Logic (in order):
    1. If the *country field* is populated and non-ambiguous:
       a. If it matches an allowed token → accept.
       b. If it matches a blocked token → reject (unless the *title* also
          mentions an allowed token, which would override).
       c. If it contains "africa" → accept (broad Africa-wide scope).
       d. Otherwise (specific unrecognised country) → reject.
    2. If the country field is empty / ambiguous:
       a. Scan the *title* for blocked tokens; reject if found and no allowed
          token is present in the title.
       b. Otherwise accept (defer to LLM).
    """
    country_n = (country or "").lower().strip()
    title_n = (title or "").lower()
    desc_n = (description or "").lower()[:500]  # only first 500 chars for perf

    # --- 1. Country field is populated ---
    if country_n and country_n not in _AMBIGUOUS_VALUES:

        # 1a. Allowed match
        for token in _ALLOWED_TOKENS:
            if token in country_n:
                return True

        # 1b. Blocked match — but let title override
        for token in _BLOCKED_TOKENS:
            if token in country_n:
                # Title rescue: if title explicitly names an allowed country, keep
                if _title_has_allowed_token(title_n):
                    logger.debug(
                        "geo_filter: blocked country=%r overridden by title allowed token", country
                    )
                    return True
                logger.info(
                    "geo_filter: REJECT country=%r (blocked token=%r) title=%r",
                    country, token, title[:80],
                )
                return False

        # 1c. "africa" anywhere in country → broad scope, accept
        if "africa" in country_n:
            return True

        # 1d. Specific unrecognised country → reject
        if len(country_n) > 3:
            if _title_has_allowed_token(title_n):
                return True
            logger.info(
                "geo_filter: REJECT country=%r (not in allowed list) title=%r",
                country, title[:80],
            )
            return False

    # --- 2. Country field is empty / ambiguous → scan title ---
    if title_n:
        for token in _BLOCKED_TOKENS:
            if token in title_n:
                # Allowed token in title can rescue
                if _title_has_allowed_token(title_n):
                    return True
                logger.info(
                    "geo_filter: REJECT via title blocked token=%r title=%r",
                    token, title[:80],
                )
                return False

    # Ambiguous or no geographic signal → defer to LLM
    return True


def _title_has_allowed_token(title_lower: str) -> bool:
    """Return True if the (lowercased) title contains at least one allowed geo token."""
    for token in _ALLOWED_TOKENS:
        if token in title_lower:
            return True
    return False


def required_country_from_page_url(page_url: str) -> str | None:
    """
    Extract a strict geography override encoded in a monitored page URL.

    Supported controls:
    - AfDB strict country: ``afdb_country=ethiopia``
    - Generic strict scope: ``geo_scope=east_africa`` (or ``geo_scope=ethiopia``)
    - World Bank helper alias: ``wb_region=east_africa``

    Example:
        https://www.afdb.org/en/projects-and-operations/procurement?afdb_country=ethiopia
        https://www.afdb.org/en/projects-and-operations/procurement#afdb_country=ethiopia
        https://www.worldbank.org/en/projects-operations/procurement?srce=both&wb_region=east_africa
    """
    raw_url = (page_url or "").strip()
    if not raw_url:
        return None

    parsed = urlparse(raw_url)
    params = parse_qs(parsed.query)
    raw = ((params.get("afdb_country") or [""])[0]).strip().lower()
    if not raw:
        frag_params = parse_qs((parsed.fragment or "").lstrip("#"))
        raw = ((frag_params.get("afdb_country") or [""])[0]).strip().lower()
    if raw:
        return raw

    scope_raw = ((params.get("geo_scope") or params.get("wb_region") or [""])[0]).strip().lower()
    if not scope_raw:
        frag_params = parse_qs((parsed.fragment or "").lstrip("#"))
        scope_raw = ((frag_params.get("geo_scope") or frag_params.get("wb_region") or [""])[0]).strip().lower()
    if not scope_raw:
        return None

    normalized = scope_raw.replace("-", "_").replace(" ", "_")
    aliases = {
        "east_africa": "east_africa",
        "eastafrica": "east_africa",
        "africa_east": "east_africa",
        "eastern_and_southern_africa": "east_africa",
        "esa": "east_africa",
        "ethiopia": "ethiopia",
    }
    return aliases.get(normalized)


def is_specific_country_allowed(
    required_country: str,
    country: str,
    title: str = "",
    description: str = "",
) -> bool:
    """
    Strict country gate for sources where URL-level filter state is encoded.

    This is intentionally conservative: if strict country is set, only notices
    with clear evidence of that country are accepted.
    """
    wanted = (required_country or "").strip().lower()
    if not wanted:
        return True

    country_n = (country or "").lower()
    title_n = (title or "").lower()
    desc_n = (description or "").lower()[:500]
    hay = f"{country_n}\n{title_n}\n{desc_n}"

    if wanted == "ethiopia":
        # Explicit country field takes precedence.
        if country_n and country_n not in _AMBIGUOUS_VALUES:
            # Keep multinational rows when Ethiopia is explicitly included in
            # title/description; otherwise require Ethiopia in country field.
            if "multinational" in country_n:
                return any(token in hay for token in ("ethiopia", "ethiopian", "addis ababa"))
            if not any(token in country_n for token in ("ethiopia", "ethiopian")):
                return False
        return any(token in hay for token in ("ethiopia", "ethiopian", "addis ababa"))

    if wanted == "east_africa":
        return _is_strict_east_africa_match(hay)

    return wanted in hay


def _is_strict_east_africa_match(haystack_lower: str) -> bool:
    """
    Strict East Africa matcher for URL-encoded regional overrides.

    Priority:
    1) Explicit East Africa signal   -> allow
    2) Explicit non-East-Africa signal -> reject
    3) Ambiguous / no geo signal -> allow

    World Bank listing rows can be sparse and sometimes omit country in the
    extracted snippet even when UI filters are already set. In that case we
    keep the row and rely on downstream geo checks when richer detail appears.
    """
    if not haystack_lower:
        return True
    for token in _ALLOWED_TOKENS:
        if token in haystack_lower:
            return True
    for token in _BLOCKED_TOKENS:
        if token in haystack_lower:
            return False
    return True
