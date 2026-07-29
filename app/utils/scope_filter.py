"""
Deterministic scope gates for Precise's advisory/consultancy focus.

Companion to :mod:`app.utils.geo_filter`: the LLM screens against the checklist,
and these rule-based nets catch the two recurring leaks the checklist calls out
repeatedly but that the model still gets wrong often enough to matter.

Both helpers are intentionally narrow. They only fire on unambiguous phrasing so
that genuine advisory work — including mixed notices that also mention goods — is
never dropped. When in doubt they return ``False`` and the LLM decision stands.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Individual-only roles
# ---------------------------------------------------------------------------

# Precise is a firm. Assignments addressed to a natural person cannot be bid on,
# no matter how well they score on sector or geography.
_INDIVIDUAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bindividual\s+(consultant|contractor|expert|specialist|adviser|advisor)s?\b"),
    re.compile(r"\bconsultant\s*\(\s*individual\s*\)"),
    re.compile(r"\b(national|international)\s+individual\s+(consultant|contractor)s?\b"),
    re.compile(r"\bindividual\s+consultancy\b"),
    re.compile(r"\bIC\s+recruitment\b", re.IGNORECASE),
)

# Phrases that show firms are in scope after all — these veto the patterns above,
# which protects notices like "individual consultants or firms may apply".
_FIRM_ELIGIBLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(firms?|companies|companys|organisations?|organizations?|institutions?)\s+(are\s+)?(also\s+)?(invited|eligible|encouraged|may\s+apply)\b"),
    re.compile(r"\bor\s+(consulting\s+)?firms?\b"),
    re.compile(r"\bfirms?\s+or\s+individuals?\b"),
    re.compile(r"\bindividuals?\s+(and|or)\s+(consulting\s+)?firms?\b"),
    re.compile(r"\b(request\s+for\s+proposals?|rfp)\b.*\bfirms?\b"),
)


# Job-advert phrasing. Some portals publish staff vacancies alongside tenders,
# and those never use the word "individual" — they read like a job description
# ("Recruitment of a senior environmental expert...").
#
# Kept deliberately short. Phrases that also occur in legitimate firm TORs
# ("reports to the", "under the supervision of", "the role involves") are not
# usable here, and neither are HR-looking field labels such as "duty station:" —
# the UN Careers harvester stamps those onto every row it produces, including
# firm consultancies.
_JOB_POSTING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\brecruitment of (a|an|one)\b"),
    re.compile(r"\bthe (incumbent|post ?holder)\b"),
    re.compile(r"\bthis (post|position|vacancy) (is|will|reports|falls)\b"),
)

# Procurement framing that means this is a tender for a firm, not a vacancy.
_TENDER_FRAMING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(request for (proposals?|quotations?|expressions? of interest)|rfp|rfq|eoi)\b"),
    re.compile(r"\b(invitation to bid|itb|call for (proposals?|tenders?)|tender notice)\b"),
    re.compile(r"\bconsultancy services\b"),
    re.compile(r"\b(bidders?|tenderers?|proposals? must be submitted)\b"),
    re.compile(r"\bterms of reference\b"),
    re.compile(r"\b(firms?|companies|consortium|joint venture)\b"),
)


def is_individual_only_role(title: str, description: str = "") -> bool:
    """
    True when the notice is addressed to an individual person rather than a firm.

    Only the title and the opening of the description are inspected: boilerplate
    deeper in a listing page routinely mentions individual consultants for
    unrelated notices.
    """
    hay = f"{title or ''}\n{(description or '')[:600]}".lower()
    if not hay.strip():
        return False

    if any(pattern.search(hay) for pattern in _INDIVIDUAL_PATTERNS):
        if any(pattern.search(hay) for pattern in _FIRM_ELIGIBLE_PATTERNS):
            return False
        logger.info(
            "scope_filter: individual-only role detected — title=%r", (title or "")[:90]
        )
        return True

    # Job advert with no procurement framing anywhere: a staff vacancy, not a tender.
    if any(pattern.search(hay) for pattern in _JOB_POSTING_PATTERNS):
        if any(pattern.search(hay) for pattern in _TENDER_FRAMING_PATTERNS):
            return False
        logger.info(
            "scope_filter: staff vacancy detected — title=%r", (title or "")[:90]
        )
        return True

    return False


# ---------------------------------------------------------------------------
# 2. Construction / works supervision
# ---------------------------------------------------------------------------

# Civil-works oversight is routinely advertised as "consultancy services", which
# is exactly why the LLM keeps scoring it as advisory work.
_WORKS_SUPERVISION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(construction|works|site|structural|engineering)\s+supervision\b"),
    re.compile(r"\bsupervision\s+of\s+(the\s+)?(construction|civil\s+works|works|building|road|bridge|borehole|well|drilling|irrigation)"),
    re.compile(r"\bresident\s+engineer\b"),
    re.compile(r"\bclerk\s+of\s+works\b"),
    re.compile(r"\bconstruction\s+management\s+(and\s+)?supervision\b"),
    re.compile(r"\bdesign\s+and\s+supervision\s+of\b"),
)

# Advisory vocabulary that indicates a substantive non-works workstream. Presence
# of any of these keeps the notice alive for the LLM/other gates to judge.
_ADVISORY_RESCUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(business development services|bds)\b"),
    re.compile(r"\bvalue chain\b"),
    re.compile(r"\bmarket systems?\b"),
    re.compile(r"\b(sme|msme)s?\b"),
    re.compile(r"\baccess to finance\b"),
    re.compile(r"\bagribusiness\b"),
    re.compile(r"\bproductive use of energy\b"),
    re.compile(r"\b(off-?grid|mini-?grid|solar)\b"),
    re.compile(r"\bprivate sector development\b"),
    re.compile(r"\bmonitoring,?\s+evaluation\b"),
)


def is_works_supervision_only(title: str, description: str = "") -> bool:
    """
    True when the core deliverable is supervision of civil works.

    Requires the supervision signal in the title (where the deliverable is named)
    and no advisory vocabulary anywhere, so mixed advisory-plus-works packages
    survive.
    """
    title_l = (title or "").lower()
    if not title_l.strip():
        return False

    if not any(pattern.search(title_l) for pattern in _WORKS_SUPERVISION_PATTERNS):
        return False

    hay = f"{title_l}\n{(description or '')[:1200].lower()}"
    if any(pattern.search(hay) for pattern in _ADVISORY_RESCUE_PATTERNS):
        return False

    logger.info("scope_filter: works-supervision notice detected — title=%r", (title or "")[:90])
    return True
