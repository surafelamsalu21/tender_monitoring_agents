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

IMPORTANT — "Productive Use of Energy (PUE)" vs water projects:
- PUE = using off-grid/solar/clean energy to POWER productive activities: solar-powered irrigation pumps, agro-processing driven by renewable energy, SME machinery using clean electricity, cold chains powered by off-grid solar. The ENERGY aspect is central.
- "Productive Use of Water" / "Water for Food Security" / rural water wells / boreholes / irrigation infrastructure construction = WATER sector (WASH/infrastructure), NOT PUE. Score such tenders as WATER/WASH = NO for sector_relevance and mission_alignment.
- Construction supervision of water wells, boreholes, or irrigation canals = infrastructure supervision = NOT an advisory/consulting deliverable in Precise's sectors.

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
   - This is a MANDATORY criterion — score it strictly.
   - YES examples: SME growth, enterprise development, agricultural/farm productivity, industrial development, value chains, market systems, access to finance for businesses, agribusiness, energy for productive use; advisory packages including TOR-based assignments, TA, studies/surveys, BDS, MEL, strategy, sector-relevant training, policy dialogue — including mixed notices where this advisory work is substantive (see Advisory vs supply).
   - NO examples (score NO for ALL of the following):
     • Pure goods supply/delivery (vehicles, tools, equipment, spare parts, drones, cameras, sewing machines, office supplies) with no substantive advisory component
     • Construction, civil works, infrastructure (WASH/water/sanitation, roads, bridges, buildings, renovation, well drilling, boreholes)
     • Construction supervision, works supervision, engineering oversight, site supervision of civil works — even when framed as "consultancy services for construction supervision"
     • Water/WASH sector: rural water supply, boreholes, well drilling, water resilience, water for food security, sanitation — regardless of whether "Productive Use" appears in the project name
     • Monitoring, verification, or third-party monitoring (TPM) of water/WASH/infrastructure/construction/humanitarian projects
     • Media/communications (graphic design, videography, photography, film production, printing)
     • Generic services for the buyer (security guards, cleaning, catering, recruitment/HR, internal audit, translation, printing)
     • Transport sector regulation and enforcement (axle load control, road traffic, driving licences, vehicle inspection)
     • Legal/justice sector work (legal aid, court reform, rule of law, anti-corruption legal frameworks)
     • Security sector reform, peacekeeping, counter-terrorism
     • Governance and institutional reform not specifically targeting private sector or enterprise development (UNCT configuration, elections, public administration reform)
     • Social/inclusion programmes without an explicit enterprise/economic component (gender equity assessments, human rights evaluations, social protection)
     • Environmental/biodiversity/conservation work where no private sector or value-chain lens is described
     • Generic environmental impact assessment (EIA) or environmental management for infrastructure projects (roads, buildings, WASH, utilities) without an explicit private-sector/enterprise development mandate
     • General programme evaluations for UN/NGO donors that assess organizational effectiveness, donor portfolio outcomes, or social programme results rather than firm/farm/industry outcomes
     • Impact evaluation, tracer study, baseline survey, or verification of a programme described only as "a development programme", "a resilience programme", or similarly vague — with no explicit mention that the programme is in energy, agriculture, SME/enterprise finance, or climate sectors
     • Architecture, engineering, or construction supervision without an advisory/BDS/TA component
   - KEY TEST: Ask "Does the core deliverable help firms, farms, or industries operate better, grow, or access markets/finance?" If NO → score NO.
   (JSON key: mission_alignment)

2. Sector Relevance
   - Is it connected to at least one:
     - Off-grid energy (solar, mini-grid, distributed renewable energy, energy access — NOT generic rural electrification through grid extension unless explicitly off-grid)
     - Agriculture / agribusiness (helping farmers, agribusinesses, cooperatives increase productivity, access markets, or develop value chains — NOT water supply infrastructure for irrigation)
     - Health electrification (solar for health facilities, cold chain for vaccines, medical equipment powered by off-grid energy)
     - Cross-cutting (e.g., SME finance, climate finance, blended finance, MSME development, market systems — NOT generic rural development or social protection)
   - YES means the WORK ITSELF is in one of these sectors. The buyer's broader portfolio does not count.
   - WATER/WASH IS NOT A YES SECTOR: Rural water supply, water resilience, boreholes, wells, water for food security, WASH (water, sanitation, hygiene) = NO for sector_relevance. These are WASH/infrastructure, not agriculture or energy.
   - GENERIC ENVIRONMENT IS NOT A YES SECTOR: Biodiversity, conservation, natural resources management without a private sector/enterprise/value-chain angle = NO. Generic EIA = NO.
   - GENERIC "DEVELOPMENT PROGRAMME" IS NOT A SECTOR: If the text describes a programme only as "development", "resilience", "humanitarian", or "social" without specifying energy/agri/SME/climate, score NO.
   - NO if the work is in another sector (e.g. WASH/water/sanitation infrastructure, rural water supply/resilience, civil works/construction, well/borehole drilling, humanitarian logistics, peacekeeping, generic IT, media production, education systems unrelated to enterprise/finance, health-service delivery without an electrification angle, general social programmes).
   (JSON key: sector_relevance)

3. Activity Fit
   - Does it include at least one of the following:
     - Private sector development / SMEs
     - Business Development Services (BDS)
     - Access to finance
     - Value chain / market systems
     - Climate-smart / regenerative agriculture
     - Productive Use of Energy (PUE)
     - Research / surveys / studies (ONLY on topics in criterion 2 sectors)
     - Capacity building / training (ONLY on topics in criterion 2 sectors)
     - Policy / stakeholder engagement (ONLY relating to criterion 2 sectors)
     - TOR-driven consulting assignments, technical assistance (TA), MEL, strategy (ONLY in criterion 2 sectors)
   - The CORE DELIVERABLE must be one of the items above (or a substantive advisory component in a mixed notice — see Advisory vs supply). Generic mention of "training" or "study" inside an unrelated tender does not count.
   - SECTOR FILTER: "Research / surveys / studies", "capacity building / training", "evaluation", "tracer study", "baseline survey", "impact evaluation", "verification", "third-party monitoring (TPM)", and "lessons learned" must be on a topic DIRECTLY relevant to criterion 2 sectors (energy, agriculture, finance, SMEs, climate). The same activity type on an UNRELATED topic (WASH/water, rural resilience, legal inclusion, transport, gender equity, biodiversity, UNCT organizational management, generic "development programme") is NO.
   - CRITICAL: An evaluation / tracer study / verification of a "development programme" or "rural resilience project" or "water project" does NOT qualify even if it uses MEL language. The SUBJECT of the evaluation must explicitly be energy, agriculture, SME/enterprise, or climate.
   - NO examples:
     • Pure goods supply, delivery, or installation with no substantive advisory component
     • Construction, civil works, infrastructure, well drilling, boreholes
     • Construction supervision / works supervision / site engineering oversight (even when called "consultancy")
     • Monitoring, verification, third-party monitoring (TPM) of water, WASH, infrastructure, or humanitarian projects
     • Impact evaluation / tracer study / baseline of a programme described only as "development", "resilience", "water", or "rural" without sector specificity in energy/agri/SME/climate
     • Generic environmental impact assessment (EIA) for infrastructure/WASH/construction without an explicit private-sector/enterprise link
     • Graphic design, videography, photography, film/media production
     • Recruitment/HR placement, internal audit/accounting, legal drafting, translation, printing
     • Vehicle/equipment supply, security, cleaning
     • Evaluation of donor portfolio effectiveness on inclusion, gender, or human rights (unrelated to criterion 2 sectors)
     • Organizational/institutional setup of UN country teams or government agencies
     • Road transport safety, axle load enforcement, driving training
     • Legal aid framework development, court/justice system reform
   (JSON key: activity_fit)

4. Geographic Fit
   - This criterion is MANDATORY for inclusion.
   - The WORK ITSELF must be in one or more of these countries only:
     Burundi, Comoros, Djibouti, Eritrea, Ethiopia, Kenya, Rwanda, Somalia, South Sudan, Sudan, Tanzania, Uganda, Seychelles, Madagascar.
   - Ethiopia is the PRIMARY focus. East Africa is the SECONDARY focus.
   - Africa-wide opportunities count as YES only when at least one country from the list above is explicitly listed as eligible or included.
   - NO when the work is located outside this region:
     • Europe: e.g. Montenegro, Albania, Serbia, Italy, France, Germany, Spain, UK, Brindisi
     • Asia: e.g. Sri Lanka, India, Pakistan, Bangladesh, Nepal, Vietnam, Philippines, Indonesia, China
     • Pacific: e.g. Papua New Guinea, Fiji, Australia
     • Americas: e.g. Brazil, Colombia, Peru, Mexico, Haiti, United States, Canada
     • Caribbean: e.g. Jamaica, Trinidad
     • Middle East: e.g. Yemen, Iraq, Syria, Jordan, Saudi Arabia, UAE
     • West Africa: e.g. Nigeria, Ghana, Senegal, Côte d'Ivoire, Mali
     • Central Africa: e.g. DRC, Cameroon, Congo
     • Southern Africa: e.g. South Africa, Zimbabwe, Zambia, Mozambique, Angola
     • North Africa: e.g. Egypt, Libya, Morocco, Algeria, Tunisia
   - If the title or description names a non-East-African country/city as the place of work, geographic_fit is NO regardless of which organization is buying.
   - STRICT RULE: Do NOT set geographic_fit=true for a tender whose primary work location is a country NOT in the allowed list above, even if the funder is an East African organization or the page contains other East African content.
   (JSON key: geographic_fit)

5. Eligibility (Quick Check)
   - YES when for-profit consulting firms are eligible, OR eligibility is unclear (and not explicitly restricted to a single category).
   - NO if explicitly restricted to: NGOs only, UN agencies only, government agencies only, universities only, or INDIVIDUALS only.
   - CRITICAL: Roles titled "Individual Consultant", "Individual Contractor", "National Individual Consultant", "International Individual Consultant", or similar are RESTRICTED TO INDIVIDUAL PERSONS, not to firms. Score eligibility_quick_check = NO for all such roles — a consulting firm cannot apply.
   - YES examples: "Request for Proposal from firms/companies", "Consulting firm", "Expression of Interest from organisations", eligibility not mentioned.
   - NO examples: "Individual consultant assignment", "Individual contractor", "National consultant (individual)", "Person with X expertise".
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
