"""
Precise screening checklist — shared wording for LLM system prompts.

Keeps Agent 1 implementations aligned with the written Screening Checklist document.
"""

PRECISE_SCREENING_CHECKLIST_MARKDOWN = """=== Screening Checklist for initial filtering of potential opportunities ===

Purpose
- To identify and shortlist relevant opportunities for further review.

Always write user-visible text fields (title, description, step3 strings) in English.

Multilingual sources (read in any language; output in English only)
- CONTENT may be in any language (e.g. French, Arabic, Amharic, Portuguese, Kiswahili) or mixed with English.
- Evaluate Step 1–3 using the meaning of the source text. Do not skip a real procurement opportunity only because it is not in English.
- Translate mentally: every string YOU output — root-level `title`, `description`, all `screening.step3` text fields (`title`, `source`, `country`, `estimated_budget` when textual, etc.) — must be clear professional English summaries of the notice.
- For dates, currencies, eligibility, and geography, derive them from source meaning; normalize country and deadline into English-era conventions (deadline ISO YYYY-MM-DD when possible).

Optional tagging
- When the dominant language of THAT opportunity notice (not boilerplate/footer) is not English or is visibly mixed, set `screening.source_language` to a short ISO 639-1-style code (`en`, `fr`, `ar`, `am`, `pt`, `sw`, …) or `mixed` / `unknown`. Omit or use `en` when the substantive notice body is entirely English.

Advisory vs supply (read before Step 1)

- Advisory / consulting (what Precise prioritizes): substantive work such as Terms of Reference / TOR, technical assistance (TA), studies / surveys / assessments, Business Development Services (BDS), MEL (monitoring, evaluation, learning), strategy, training on topics aligned with sector criterion 2, policy dialogue / stakeholder engagement, and similar analytical or capacity-building deliverables — not merely handing over goods.
- Supply / goods-heavy: the primary or sole deliverable is procurement or delivery of equipment, vehicles, commodities, bulk software licensing, construction materials, or comparable goods, without a substantive advisory/consulting workstream described in the notice.
- Mixed notices (advisory + supply in the same notice): Score mission_alignment and activity_fit YES if the advisory/consulting component alone would satisfy those criteria (geography and sectors). Do not answer NO solely because the notice also lists goods or installation. If the text is only supply/installation with no substantive TOR/TA/study/BDS/MEL/strategy/training/policy line items, score those criteria NO.

Step 1: Quick Relevance Filter (Yes / No)

Score each of the 5 criteria below as YES or NO, then compute yes_count (0–5).

Output rule for WHAT TO INCLUDE in your JSON array:
- KEEP / INCLUDE the opportunity ONLY when yes_count >= 3.
- OMIT the opportunity entirely when yes_count is 0, 1, or 2.
- HARD GEO GATE: INCLUDE only when geographic_fit = YES for one or more of these countries: Burundi, Comoros, Djibouti, Eritrea, Ethiopia, Kenya, Rwanda, Somalia, South Sudan, Tanzania, Uganda, Seychelles, Madagascar. If geographic_fit = NO, OMIT even if yes_count >= 3.

How to score honestly:
- Score each criterion based on what the title and description ACTUALLY describe — not on optimistic interpretation.
- A criterion is YES only when there is concrete textual evidence for it. If the text is silent, it is NO.
- The buyer being a development organization does NOT automatically make any criterion YES.

1. Mission Alignment
   - Does it relate to economic development of firms, farms, or industries?
   - YES examples: SME growth, enterprise development, agricultural/farm productivity, industrial development, value chains, market systems, access to finance for businesses, agribusiness, energy for productive use; advisory packages including TOR-based assignments, TA, studies/surveys, BDS, MEL, strategy, sector-relevant training, policy dialogue — including mixed notices where this advisory work is substantive (see Advisory vs supply).
   - NO examples: pure goods supply (vehicles, equipment, spare parts, calibration systems, office supplies) with no substantive advisory component; construction or infrastructure works (water/sanitation/WASH, roads, buildings); media/communications work (graphic design, videography, photography); generic services for the buyer organization itself (security, cleaning, catering, recruitment, audit, translation, printing).
   (JSON key: mission_alignment)

2. Sector Relevance
   - Is it connected to at least one:
     - Off-grid energy
     - Agriculture / agribusiness
     - Health electrification
     - Cross-cutting (e.g., finance, climate, SMEs)
   - YES means the WORK ITSELF is in one of these sectors. The buyer's broader portfolio does not count.
   - NO if the work is in another sector (e.g. WASH/water/sanitation infrastructure, civil works/construction, humanitarian logistics, peacekeeping, generic IT, media production, education systems unrelated to enterprise/finance, health-service delivery without an electrification angle).
   (JSON key: sector_relevance)

3. Activity Fit
   - Does it include at least one of the following:
     - Private sector development / SMEs
     - Business Development Services (BDS)
     - Access to finance
     - Value chain / market systems
     - Climate-smart / regenerative agriculture
     - Productive Use of Energy (PUE)
     - Research / surveys / studies
     - Capacity building / training
     - Policy / stakeholder engagement
     - TOR-driven consulting assignments, technical assistance (TA), MEL (monitoring, evaluation, learning), strategy formulation
   - The CORE DELIVERABLE must be one of the items above (or a substantive advisory component in a mixed notice — see Advisory vs supply). Generic mention of "training" or "study" inside an unrelated tender does not count.
   - "Capacity building / training" and "Research / surveys / studies" must be on a topic relevant to the sectors in criterion 2 (energy, agriculture, finance, SMEs, climate). Training in graphic design, photography, communications, generic IT use, language, or driving is NO.
   - NO for: pure goods supply/delivery/installation with no substantive advisory line items, construction/civil works, graphic design, videography, photography, film/media production, recruitment/HR placement, audit/accounting, legal drafting, translation, printing, vehicle supply, security guards, cleaning.
   (JSON key: activity_fit)

4. Geographic Fit
   - This criterion is MANDATORY for inclusion.
   - The WORK ITSELF must be in one or more of these countries only:
     Burundi, Comoros, Djibouti, Eritrea, Ethiopia, Kenya, Rwanda, Somalia, South Sudan, Tanzania, Uganda, Seychelles, Madagascar.
   - Africa-wide opportunities count as YES only when at least one country from the list above is explicitly listed as eligible or included.
   - NO when the work is located outside this region: Asia, Pacific Islands (e.g. Papua New Guinea), Americas, Caribbean, Europe (e.g. Italy, Brindisi), Middle East, or West/Central/Southern/North Africa only (e.g. Nigeria, Senegal, Ghana, Egypt, South Africa, DRC).
   - If the title or description names a non-East-African country/city as the place of work, geographic_fit is NO regardless of which organization is buying.
   (JSON key: geographic_fit)

5. Eligibility (Quick Check)
   - YES when for-profit consulting firms are eligible, OR eligibility is unclear (and not explicitly restricted).
   - NO if explicitly restricted to NGOs only, UN agencies only, government agencies only, universities only, or individuals only.
   (JSON key: eligibility_quick_check)

Step 2: Quick Flags (Do NOT eliminate — tag only)

These help later decisions. Never drop an opportunity because of Step 2.

Opportunity characteristics — use these exact tokens in opportunity_characteristics[]:
- large_program (large program / multi-year / multi-million)
- small_quick_assignment (small / quick assignment)
- research_heavy (research-heavy)
- implementation_heavy (implementation-heavy)
- consortium_likely_required (consortium likely required)

Strategic signals — use these exact tokens in strategic_signals[]:

Required — include exactly ONE engagement tag (advisory vs supply classification):
- engagement_advisory_only (advisory/consulting is the core; goods mentions minor or absent)
- engagement_supply_only (supply/goods is the core; no substantive TOR/TA/study/BDS/MEL/strategy/training/policy advisory deliverables)
- engagement_advisory_and_supply_mixed (both a substantive advisory/consulting component and a supply/goods component are clearly in scope)

Optional — include zero or more:
- new_donor_for_precise (new donor for Precise)
- repeat_known_donor (repeat / known donor)
- government_led (government-led)
- private_sector_focused (private sector-focused)

Potential concerns — use these exact tokens in potential_concerns[]:
- very_short_deadline_lt_2_weeks (very short deadline, under 2 weeks)
- broad_or_unclear_scope (very broad / unclear scope)
- heavy_compliance_language (heavy compliance language)

Step 3: Basic Information Capture

For each INCLUDED opportunity, fill Step 3:

- Opportunity title
- Source (donor/platform)
- Country
- Type: Grant | Consultancy | Other (JSON: grant | consultancy | other)
- Deadline
- Estimated budget (if available)
- Link / document
- description: brief summary in English
"""
