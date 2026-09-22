"""
Playwright harvest: optional form login from .env, then open monitored listing URL.

Set on the MonitoredPage (API) or fall back to Settings:
- auth_login_url, auth_username_env, auth_password_env
- auth_form_selectors_json: {"username":"css","password":"css","submit":"css"}

Put real credentials only in .env, e.g. CRAWL_AUTH_USERNAME / CRAWL_AUTH_PASSWORD.
Run once:  playwright install chromium
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from app.core.config import settings
from app.crawl.types import HarvestResult
from app.crawl.worldbank_procurement import (
    worldbank_notice_detail_url,
    worldbank_notice_passes_consulting_prefilter,
    worldbank_notice_to_listing_row,
)
from app.models.page import MonitoredPage

logger = logging.getLogger(__name__)
_MIN_PAGE_ATTEMPTS = 2
_TRANSIENT_NETWORK_MARKERS = (
    "err_name_not_resolved",
    "err_internet_disconnected",
    "err_connection_refused",
    "err_connection_reset",
    "err_connection_timed_out",
    "err_network_changed",
    "err_address_unreachable",
    "net::err_",
)


def _is_transient_network_error(error: str | None) -> bool:
    low = (error or "").lower()
    return any(marker in low for marker in _TRANSIENT_NETWORK_MARKERS)


async def _goto_with_retry(page, url: str, *, wait_until: str, timeout: int | None = None):
    """Retry once on transient DNS/network faults before surfacing the error."""
    goto_kwargs: dict = {"wait_until": wait_until}
    if timeout is not None:
        goto_kwargs["timeout"] = timeout
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            return await page.goto(url, **goto_kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt == 0 and _is_transient_network_error(str(exc)):
                logger.warning(
                    "Transient network error on goto(%s, %s): %s; retrying once.",
                    url,
                    wait_until,
                    exc,
                )
                await asyncio.sleep(2)
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"goto failed for {url}")


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def _extract_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        abs_url = urljoin(base_url, href)
        if abs_url.startswith("http"):
            out.append(abs_url)
    return list(dict.fromkeys(out))


def _undp_region_filter_id(listing_url: str) -> str | None:
    """Support URLs like https://procurement-notices.undp.org/?region=RAF."""
    parsed = urlparse(listing_url)
    if parsed.netloc.lower() != "procurement-notices.undp.org":
        return None

    params = parse_qs(parsed.query)
    raw = (
        (params.get("region") or params.get("undp_region") or [""])[0]
        or parsed.fragment
    ).strip()
    if not raw:
        return None

    normalized = raw.lower().replace("region_", "").replace("-", "_")
    region_map = {
        "raf": "region_RAF",
        "africa": "region_RAF",
        "rab": "region_RAB",
        "arab_states": "region_RAB",
        "rap": "region_RAP",
        "asia_and_the_pacific": "region_RAP",
        "rec": "region_REC",
        "europe_cis": "region_REC",
        "rblac": "region_RBLAC",
        "latin_america_and_the_caribbean": "region_RBLAC",
    }
    return region_map.get(normalized)


def _is_worldbank_procurement_url(url: str) -> bool:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower()
    return (
        "worldbank.org" in host
        and "/projects-operations/procurement" in parsed.path.lower()
    )


def _worldbank_scope_filter_value(listing_url: str) -> str | None:
    """
    Support URL-encoded local filter hints for World Bank procurement listings.

    Example:
      https://www.worldbank.org/en/projects-operations/procurement?srce=both&geo_scope=ethiopia

    We only honor dedicated local keys (`wb_region` / `geo_scope`) so existing
    site query params remain untouched.
    """
    if not _is_worldbank_procurement_url(listing_url):
        return None

    parsed = urlparse(listing_url)
    params = parse_qs(parsed.query)
    raw = ((params.get("wb_region") or params.get("geo_scope") or [""])[0]).strip()
    if not raw:
        frag_params = parse_qs((parsed.fragment or "").lstrip("#"))
        raw = ((frag_params.get("wb_region") or frag_params.get("geo_scope") or [""])[0]).strip()
    if not raw:
        return None

    normalized = raw.lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "east_africa": "east_africa",
        "eastafrica": "east_africa",
        "africa_east": "east_africa",
        "eastern_and_southern_africa": "east_africa",
        "esa": "east_africa",
        "ethiopia": "ethiopia",
        "ethiopian": "ethiopia",
    }
    return aliases.get(normalized)


async def _apply_worldbank_region_filter(page, listing_url: str) -> str | None:
    scope = _worldbank_scope_filter_value(listing_url)
    if scope not in ("east_africa", "ethiopia"):
        return None

    targets_by_scope = {
        "east_africa": [
            "east africa",
            "africa east",
            "eastern and southern africa",
        ],
        "ethiopia": [
            "ethiopia",
            "ethiopian",
        ],
    }
    targets = targets_by_scope.get(scope) or []

    applied = await page.evaluate(
        """(targets) => {
            const normalize = (s) => String(s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
            const body = Array.from(document.querySelectorAll('label, a, button, li, span, div, input'));
            const visible = (el) => {
                const st = window.getComputedStyle(el);
                return st && st.display !== 'none' && st.visibility !== 'hidden';
            };
            const score = (txt) => {
                const t = normalize(txt);
                if (!t) return 0;
                if (targets.some((x) => t === x || t.startsWith(x + ' ') || t.includes(x + ' ('))) return 3;
                if (targets.some((x) => t.includes(x))) return 2;
                return 0;
            };
            let best = null;
            let bestScore = 0;
            for (const el of body) {
                if (!visible(el)) continue;
                const direct = normalize(el.textContent || '');
                let s = score(direct);
                if (el.tagName.toLowerCase() === 'input') {
                    const id = el.getAttribute('id');
                    if (id) {
                        const lbl = document.querySelector(`label[for="${id}"]`);
                        if (lbl) s = Math.max(s, score(lbl.textContent || ''));
                    }
                }
                if (s > bestScore) {
                    best = el;
                    bestScore = s;
                }
            }
            if (!best || bestScore <= 0) return null;

            const clickInput = (inputEl) => {
                if (!inputEl) return false;
                const typ = String(inputEl.getAttribute('type') || '').toLowerCase();
                if (typ !== 'checkbox' && typ !== 'radio') return false;
                if (!inputEl.checked) inputEl.click();
                inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                inputEl.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            };

            let clicked = false;
            if (best.tagName.toLowerCase() === 'input') {
                clicked = clickInput(best);
            }
            if (!clicked) {
                const nested = best.querySelector('input[type="checkbox"], input[type="radio"]');
                if (nested) clicked = clickInput(nested);
            }
            if (!clicked) {
                const wrap = best.closest('label, button, a, [role="button"], li, div');
                if (wrap) {
                    wrap.click();
                    clicked = true;
                }
            }
            if (!clicked) return null;

            // Attempt explicit apply button if the listing UI needs it.
            const applyBtn = Array.from(
                document.querySelectorAll('button, input[type="button"], input[type="submit"], a')
            ).find((el) => {
                const txt = normalize(
                    el.tagName.toLowerCase() === 'input' ? el.getAttribute('value') : el.textContent
                );
                return txt === 'apply' || txt.includes('apply filter') || txt.includes('show');
            });
            if (applyBtn) applyBtn.click();
            return targets[0] || 'matched_scope';
        }""",
        targets,
    )
    if applied:
        # World Bank listing refresh is async and can lag after facet clicks.
        await page.wait_for_timeout(1800)
        return scope
    return None


_WB_PROCNOTICES_API = "https://search.worldbank.org/api/v2/procnotices"
_WB_API_ROWS_PER_PAGE = 50
_WB_SCOPE_COUNTRY_NAMES: dict[str, list[str]] = {
    "ethiopia": ["Ethiopia"],
    "east_africa": [
        "Ethiopia",
        "Kenya",
        "Uganda",
        "Tanzania",
        "Rwanda",
        "Burundi",
        "Somalia, Federal Republic of",
        "Djibouti",
        "Eritrea",
        "South Sudan",
        "Sudan",
        "Seychelles",
        "Madagascar",
        "Comoros",
    ],
}


def _worldbank_api_country_names(scope: str) -> list[str]:
    return list(_WB_SCOPE_COUNTRY_NAMES.get(scope) or [])


def _worldbank_notice_detail_url(notice_id: str) -> str:
    return worldbank_notice_detail_url(notice_id)


def _worldbank_procnotices_fetch(*, country: str, offset: int, rows: int) -> dict:
    query = urlencode(
        [
            ("format", "json"),
            ("project_ctry_name", country),
            ("rows", str(rows)),
            ("os", str(offset)),
        ],
        quote_via=quote,
    )
    url = f"{_WB_PROCNOTICES_API}?{query}"
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            )
        },
    )
    with urlopen(req, timeout=45) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    if not isinstance(payload, dict):
        raise ValueError("World Bank procnotices API returned non-object JSON")
    return payload


def _worldbank_format_notice_row(notice: dict) -> tuple[str, str | None]:
    listing = worldbank_notice_to_listing_row(notice)
    if not listing:
        return "", None
    title = listing["title"]
    country = listing.get("country") or "unknown"
    detail_url = listing.get("detail_url")
    notice_type = str(notice.get("notice_type") or "").strip()
    notice_date = listing.get("publication_date") or ""
    project = str(notice.get("project_name") or "").strip()
    project_id = str(notice.get("project_id") or "").strip()
    language = str(notice.get("notice_lang_name") or "").strip()
    project_title = f"{project} - {project_id}".strip(" -") if project or project_id else ""
    table_row = " | ".join(
        part for part in (title, country, project_title, notice_type, language, notice_date) if part
    )
    lines = [
        f"- {title}",
        f"  - Country: {country}",
    ]
    if project_title:
        lines.append(f"  - Project: {project_title}")
    if notice_type:
        lines.append(f"  - Notice type: {notice_type}")
    if notice_date:
        lines.append(f"  - Date: {notice_date}")
    if detail_url:
        lines.append(f"  - Link: {detail_url}")
    if listing.get("snippet"):
        lines.append(f"  - Summary: {listing['snippet']}")
    if table_row:
        lines.append(f"  - Row: {table_row}")
    return "\n".join(lines), detail_url


def _worldbank_api_harvest_sync(
    scope: str,
    max_pages: int,
) -> tuple[str, list[str], str, int, list[dict], dict[str, int]]:
    """
    Harvest World Bank procurement notices via the official search API.

    Uses ``project_ctry_name`` (same facet the public listing UI exposes).
    """
    countries = _worldbank_api_country_names(scope)
    if not countries:
        raise ValueError(f"Unsupported World Bank API scope: {scope!r}")

    pages = max(_MIN_PAGE_ATTEMPTS, min(int(max_pages or _MIN_PAGE_ATTEMPTS), 6))
    rows = _WB_API_ROWS_PER_PAGE
    multi_country = len(countries) > 1

    markdown_rows: list[str] = []
    structured_rows: list[dict] = []
    links: list[str] = []
    seen_links: set[str] = set()
    seen_ids: set[str] = set()
    api_pages_fetched = 0
    reported_total: int | None = None
    prefilter_stats = {"raw_seen": 0, "prefilter_kept": 0, "prefilter_dropped": 0}

    for country in countries:
        country_pages = 1 if multi_country else pages
        for page_idx in range(country_pages):
            offset = page_idx * rows
            try:
                payload = _worldbank_procnotices_fetch(country=country, offset=offset, rows=rows)
            except Exception as exc:
                logger.warning(
                    "World Bank API fetch failed scope=%s country=%r offset=%s: %s",
                    scope,
                    country,
                    offset,
                    exc,
                )
                break
            api_pages_fetched += 1
            if reported_total is None and not multi_country:
                try:
                    reported_total = int(payload.get("total") or 0)
                except (TypeError, ValueError):
                    reported_total = None

            notices = payload.get("procnotices") or []
            if not notices:
                break

            for notice in notices:
                if not isinstance(notice, dict):
                    continue
                notice_id = str(notice.get("id") or "").strip()
                if notice_id and notice_id in seen_ids:
                    continue
                if notice_id:
                    seen_ids.add(notice_id)
                prefilter_stats["raw_seen"] += 1
                if not worldbank_notice_passes_consulting_prefilter(notice):
                    prefilter_stats["prefilter_dropped"] += 1
                    continue
                prefilter_stats["prefilter_kept"] += 1
                listing = worldbank_notice_to_listing_row(notice)
                if listing:
                    structured_rows.append(listing)
                row_md, detail_url = _worldbank_format_notice_row(notice)
                if row_md:
                    markdown_rows.append(row_md)
                if detail_url and detail_url not in seen_links:
                    seen_links.add(detail_url)
                    links.append(detail_url)

            if len(notices) < rows:
                break

    body = (
        "World Bank procurement API harvest.\n\n"
        f"Scope: {scope}\n"
        f"Countries queried: {', '.join(countries)}\n"
        f"API pages fetched: {api_pages_fetched}\n"
        f"Reported total (primary country): {reported_total if reported_total is not None else 'n/a'}\n"
        f"Raw notices scanned: {prefilter_stats['raw_seen']}\n"
        f"Consulting pre-filter kept: {prefilter_stats['prefilter_kept']}\n"
        f"Consulting pre-filter dropped: {prefilter_stats['prefilter_dropped']}\n\n"
        "Description | Country | Project Title | Notice Type | Language | Published Date\n"
        + "\n".join(markdown_rows[:400])
    )
    raw_json = json.dumps(
        {
            "scope": scope,
            "countries": countries,
            "reported_total": reported_total,
            "notice_count": prefilter_stats["prefilter_kept"],
            "prefilter_stats": prefilter_stats,
        }
    )
    return body, links, raw_json, max(api_pages_fetched, 1), structured_rows, prefilter_stats


async def _worldbank_api_harvest(
    scope: str,
    max_pages: int,
) -> tuple[str, list[str], str, int, list[dict], dict[str, int]]:
    return await asyncio.to_thread(_worldbank_api_harvest_sync, scope, max_pages)


async def _apply_undp_region_filter(page, listing_url: str) -> str | None:
    region_id = _undp_region_filter_id(listing_url)
    if not region_id:
        return None

    applied = await page.evaluate(
        """(regionId) => {
            const el = document.querySelector(`#${regionId}`);
            if (!el) return false;
            el.checked = true;
            el.dispatchEvent(new Event('change', { bubbles: true }));
            if (typeof window.set_filter === 'function') window.set_filter();
            return true;
        }""",
        region_id,
    )
    if applied:
        await page.wait_for_timeout(500)
        return region_id
    return None


def _afdb_country_filter_value(listing_url: str) -> str | None:
    """
    Support URLs like:
      https://www.afdb.org/en/projects-and-operations/procurement?afdb_country=ethiopia

    The AfDB listing applies country via in-page form controls (URL usually stays
    unchanged). This helper lets us encode a target country in the monitored URL.
    """
    parsed = urlparse(listing_url)
    host = parsed.netloc.lower()
    if "afdb.org" not in host:
        return None
    if "/projects-and-operations/procurement" not in parsed.path.lower():
        return None

    params = parse_qs(parsed.query)
    raw = ((params.get("afdb_country") or params.get("country") or [""])[0]).strip()
    if not raw:
        frag_params = parse_qs((parsed.fragment or "").lstrip("#"))
        raw = ((frag_params.get("afdb_country") or frag_params.get("country") or [""])[0]).strip()
    return raw or None


async def _apply_afdb_country_filter(page, listing_url: str) -> str | None:
    country = _afdb_country_filter_value(listing_url)
    if not country:
        return None

    applied = await page.evaluate(
        """(countryName) => {
            const wanted = String(countryName || '').trim().toLowerCase();
            if (!wanted) return null;

            const allSelects = Array.from(document.querySelectorAll('select'));
            if (!allSelects.length) return null;

            const chooseOption = (selectEl) => {
                const options = Array.from(selectEl.options || []);
                let opt = options.find((o) => (o.textContent || '').trim().toLowerCase() === wanted);
                if (!opt) {
                    opt = options.find((o) => (o.value || '').trim().toLowerCase() === wanted);
                }
                if (!opt) {
                    opt = options.find((o) => (o.textContent || '').toLowerCase().includes(wanted));
                }
                return opt || null;
            };

            // Prefer a select associated with a "Country" label.
            let targetSelect = null;
            const labels = Array.from(document.querySelectorAll('label'));
            for (const label of labels) {
                const txt = (label.textContent || '').trim().toLowerCase();
                if (!txt.includes('country')) continue;
                const forId = label.getAttribute('for');
                if (forId) {
                    const byId = document.getElementById(forId);
                    if (byId && byId.tagName && byId.tagName.toLowerCase() === 'select') {
                        targetSelect = byId;
                        break;
                    }
                }
                const nested = label.querySelector('select');
                if (nested) {
                    targetSelect = nested;
                    break;
                }
            }

            // Fallback: pick a select that contains a matching option.
            if (!targetSelect) {
                targetSelect = allSelects.find((s) => !!chooseOption(s)) || null;
            }
            if (!targetSelect) return null;

            const option = chooseOption(targetSelect);
            if (!option) return null;

            targetSelect.value = option.value;
            targetSelect.dispatchEvent(new Event('input', { bubbles: true }));
            targetSelect.dispatchEvent(new Event('change', { bubbles: true }));

            const applyCandidates = Array.from(
                document.querySelectorAll('button, input[type="submit"], input[type="button"]')
            );
            const applyBtn = applyCandidates.find((el) => {
                const txt = (
                    el.tagName.toLowerCase() === 'input'
                        ? (el.getAttribute('value') || '')
                        : (el.textContent || '')
                ).trim().toLowerCase();
                return txt === 'apply' || txt.includes('apply');
            });
            if (applyBtn) {
                applyBtn.click();
            }

            return (option.textContent || '').trim() || countryName;
        }""",
        country,
    )

    if applied:
        # Give the listing widget a moment to refresh after submit.
        await page.wait_for_timeout(1200)
        return str(applied)
    return None


def _is_afdb_procurement_url(url: str) -> bool:
    parsed = urlparse(url or "")
    return "afdb.org" in parsed.netloc.lower() and "/projects-and-operations/procurement" in parsed.path.lower()


def _afdb_navigation_url(listing_url: str) -> str:
    """
    Remove local-only control params before loading AfDB.

    AfDB may propagate unknown query params (like `afdb_country`) into its AJAX
    endpoint and return 403. We keep the country hint for local automation but
    navigate using a clean URL.
    """
    parsed = urlparse(listing_url)
    if not (_is_afdb_procurement_url(listing_url) or _is_worldbank_procurement_url(listing_url)):
        return listing_url
    params = parse_qs(parsed.query, keep_blank_values=True)
    params.pop("afdb_country", None)
    params.pop("wb_region", None)
    params.pop("geo_scope", None)
    clean_q = urlencode([(k, v) for k, vals in params.items() for v in vals])
    return urlunparse((
        parsed.scheme, parsed.netloc, parsed.path,
        parsed.params, clean_q, parsed.fragment,
    ))


def _max_pages_for_listing_url(listing_url: str) -> int:
    """
    Source-aware pagination budget.
    - AfDB procurement: force up to 6 pages (user request).
    - Others: keep existing global default behavior.
    """
    configured = int(getattr(settings, "PLAYWRIGHT_MAX_PAGES", 4) or 4)
    if _is_afdb_procurement_url(listing_url):
        return max(_MIN_PAGE_ATTEMPTS, min(max(configured, 6), 6))
    return max(_MIN_PAGE_ATTEMPTS, min(configured, 4))


def _looks_like_cloudflare_challenge(text: str, html: str) -> bool:
    low = f"{text}\n{html}".lower()
    return (
        "just a moment" in low
        or "enable javascript and cookies to continue" in low
        or "/cdn-cgi/challenge-platform/" in low
        or "__cf_chl_" in low
    )


def _links_look_like_challenge_artifacts(links: list[str]) -> bool:
    if not links:
        return True
    normalized = [str(link or "").lower() for link in links]
    return all(
        ("cloudflare.com" in link) or ("challenge" in link)
        for link in normalized
    )


def _is_developmentaid_tenders_url(url: str) -> bool:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    return "developmentaid.org" in host and "/tenders/search" in path


def _is_ethiojobs_consultancy_url(url: str) -> bool:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower()
    path = parsed.path.lower().rstrip("/")
    return "ethiojobs.net" in host and path == "/jobs/consultancy"


def _is_reportertenders_listing_url(url: str) -> bool:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    return "reportertenders.com" in host and "/bid-category/" in path


def _resolve_login_url_for_page(monitored: MonitoredPage, listing_url: str) -> str | None:
    """
    Resolve login URL with safe defaults.

    Page-level `auth_login_url` always wins. The global login URL is only applied
    to DevelopmentAid pages; otherwise it can accidentally force login attempts on
    public portals such as ReporterTenders.
    """
    page_login_url = getattr(monitored, "auth_login_url", None)
    if page_login_url:
        return str(page_login_url)
    if _is_developmentaid_tenders_url(listing_url):
        return settings.PLAYWRIGHT_AUTH_LOGIN_URL
    return None


def _normalize_iso_date(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", raw)
        if m:
            return m.group(1)
    return None


def _clean_text(text: str, max_chars: int = 260) -> str:
    compact = " ".join((text or "").split()).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _set_query_param(url: str, key: str, value: str) -> str:
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params[key] = [value]
    query = urlencode([(k, v) for k, vals in params.items() for v in vals])
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment)
    )


def _developmentaid_rows_from_html(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    rows: list[dict] = []
    seen: set[str] = set()
    for a in soup.select("a[href]"):
        href = urljoin(base_url, (a.get("href") or "").strip())
        if "/tenders/view/" not in href.lower():
            continue
        title = _clean_text(a.get_text(" ", strip=True), 300)
        if len(title) < 6 or href in seen:
            continue
        seen.add(href)
        rows.append(
            {
                "title": title,
                "reference": None,
                "publication_date": None,
                "deadline": None,
                "detail_url": href,
                "country": None,
                "snippet": None,
            }
        )
    return rows


def _reportertenders_rows_from_html(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    rows: list[dict] = []
    seen: set[str] = set()
    for a in soup.select('a[href*="/bids/"]'):
        href = urljoin(base_url, (a.get("href") or "").strip())
        title = _clean_text(a.get_text(" ", strip=True), 320)
        if not title or len(title) < 8 or href in seen:
            continue
        seen.add(href)
        container = a.find_parent(["article", "li", "div"])
        container_txt = _clean_text(container.get_text(" ", strip=True), 1400) if container else ""
        m = re.search(r"(\d{2}/\d{2}/\d{4})", container_txt)
        deadline = None
        if m:
            raw = m.group(1)
            parts = raw.split("/")
            if len(parts) == 3:
                day, month, year = parts
                deadline = f"{year}-{month}-{day}"
        rows.append(
            {
                "title": title,
                "reference": None,
                "publication_date": None,
                "deadline": deadline,
                "detail_url": href,
                "country": "Ethiopia",
                "snippet": container_txt[:260] if container_txt else None,
            }
        )
    return rows


def _ethiojobs_rows_from_next_data_html(html: str) -> list[dict]:
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html or "",
        re.S,
    )
    if not match:
        return []
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    items = (
        payload.get("props", {})
        .get("pageProps", {})
        .get("initialData", [])
    )
    if not isinstance(items, list):
        return []

    rows: list[dict] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _clean_text(str(item.get("title") or ""), 300)
        slug = str(item.get("slug") or "").strip().strip("/")
        if not title or not slug:
            continue
        detail_url = f"https://ethiojobs.net/job/{slug}"
        if detail_url in seen:
            continue
        seen.add(detail_url)

        company = None
        company_obj = item.get("company")
        if isinstance(company_obj, dict):
            company = _clean_text(str(company_obj.get("name") or ""), 140) or None

        location_bits = [
            _clean_text(str(item.get("city") or ""), 120),
            _clean_text(str(item.get("state") or ""), 120),
            _clean_text(str(item.get("country") or ""), 120),
        ]
        location = ", ".join(part for part in location_bits if part)
        snippet_parts = [company or "", location]
        summary = _clean_text(
            BeautifulSoup(str(item.get("requirement") or item.get("description") or ""), "html.parser").get_text(" ", strip=True),
            240,
        )
        if summary:
            snippet_parts.append(summary)
        snippet = _clean_text(" | ".join(part for part in snippet_parts if part), 280) or None

        rows.append(
            {
                "title": title,
                "reference": None,
                "publication_date": _normalize_iso_date(item.get("date_published")),
                "deadline": _normalize_iso_date(item.get("date_expiry")),
                "detail_url": detail_url,
                "country": _clean_text(str(item.get("country") or ""), 80) or "Ethiopia",
                "snippet": snippet,
            }
        )
    return rows


def _rows_to_listing_markdown(source_name: str, source_url: str, rows: list[dict]) -> str:
    lines = [
        f"{source_name} listing harvest.",
        "",
        f"Source URL: {source_url}",
        f"Rows: {len(rows)}",
        "",
        "Title | Country | Published | Deadline | Link",
    ]
    for row in rows[:400]:
        title = str(row.get("title") or "").strip()
        country = str(row.get("country") or "unknown").strip() or "unknown"
        pub = str(row.get("publication_date") or "").strip()
        deadline = str(row.get("deadline") or "").strip()
        detail = str(row.get("detail_url") or "").strip()
        if not title or not detail:
            continue
        table_row = " | ".join(part for part in (title, country, pub, deadline, detail) if part)
        lines.append(f"- {title}")
        lines.append(f"  - Country: {country}")
        if pub:
            lines.append(f"  - Published: {pub}")
        if deadline:
            lines.append(f"  - Deadline: {deadline}")
        lines.append(f"  - Link: {detail}")
        snippet = str(row.get("snippet") or "").strip()
        if snippet:
            lines.append(f"  - Summary: {snippet}")
        lines.append(f"  - Row: {table_row}")
    return "\n".join(lines)


def _ethiojobs_harvest_sync(listing_url: str, max_pages: int) -> tuple[str, list[str], str, int, list[dict]]:
    pages = max(_MIN_PAGE_ATTEMPTS, min(int(max_pages or _MIN_PAGE_ATTEMPTS), 4))
    rows: list[dict] = []
    seen_links: set[str] = set()
    html_pages: list[str] = []
    pages_captured = 0
    for page_num in range(1, pages + 1):
        page_url = _set_query_param(listing_url, "page", str(page_num))
        req = Request(
            page_url,
            headers={
                "User-Agent": settings.DEVELOPMENTAID_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        try:
            with urlopen(req, timeout=45) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as exc:
            logger.warning("Ethiojobs fetch failed page=%s: %s", page_num, exc)
            break
        html_pages.append(html)
        page_rows = _ethiojobs_rows_from_next_data_html(html)
        if not page_rows:
            break
        added_this_page = 0
        for row in page_rows:
            detail = str(row.get("detail_url") or "").strip()
            if not detail or detail in seen_links:
                continue
            seen_links.add(detail)
            rows.append(row)
            added_this_page += 1
        pages_captured += 1
        if added_this_page == 0:
            break

    if not rows:
        raise RuntimeError("Ethiojobs parser found no listings in __NEXT_DATA__ payload.")
    markdown = _rows_to_listing_markdown("Ethiojobs consultancy", listing_url, rows)
    links = [str(row.get("detail_url")) for row in rows if row.get("detail_url")]
    return markdown, list(dict.fromkeys(links)), "\n".join(html_pages), max(pages_captured, 1), rows


async def _ethiojobs_harvest(
    listing_url: str, max_pages: int
) -> tuple[str, list[str], str, int, list[dict]]:
    return await asyncio.to_thread(_ethiojobs_harvest_sync, listing_url, max_pages)


def _developmentaid_session_harvest_sync(
    listing_url: str, max_pages: int
) -> tuple[str, list[str], str, int, list[dict]]:
    _ = max_pages  # Reserved for future paginated session crawling.
    cookie = str(getattr(settings, "DEVELOPMENTAID_SESSION_COOKIE", "") or "").strip()
    headers = {
        "User-Agent": settings.DEVELOPMENTAID_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.developmentaid.org/",
    }
    if cookie:
        headers["Cookie"] = cookie
    req = Request(listing_url, headers=headers)
    timeout_sec = int(getattr(settings, "DEVELOPMENTAID_HTTP_TIMEOUT_SEC", 45) or 45)
    try:
        with urlopen(req, timeout=timeout_sec) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        if int(getattr(exc, "code", 0) or 0) == 403:
            if cookie:
                raise RuntimeError(
                    "DevelopmentAid returned HTTP 403 with DEVELOPMENTAID_SESSION_COOKIE. "
                    "Refresh the cookie from a logged-in browser session."
                ) from exc
            raise RuntimeError(
                "DevelopmentAid returned HTTP 403. Set DEVELOPMENTAID_SESSION_COOKIE in .env "
                "from an authenticated browser session."
            ) from exc
        raise RuntimeError(f"DevelopmentAid HTTP error: {exc}") from exc
    except URLError as exc:
        raise RuntimeError(f"DevelopmentAid network error: {exc}") from exc

    text = _html_to_text(html)
    if _looks_like_cloudflare_challenge(text, html):
        if cookie:
            raise RuntimeError(
                "DevelopmentAid challenge page returned even with DEVELOPMENTAID_SESSION_COOKIE. "
                "Refresh the cookie from a logged-in browser session."
            )
        raise RuntimeError(
            "DevelopmentAid challenge page returned. Set DEVELOPMENTAID_SESSION_COOKIE in .env "
            "from an authenticated browser session."
        )

    rows = _developmentaid_rows_from_html(html, listing_url)
    if not rows:
        raise RuntimeError(
            "DevelopmentAid page loaded but no /tenders/view/ links were found. "
            "Page structure may have changed or account access is limited."
        )
    markdown = _rows_to_listing_markdown("DevelopmentAid tenders", listing_url, rows)
    links = [str(row.get("detail_url")) for row in rows if row.get("detail_url")]
    return markdown, list(dict.fromkeys(links)), html, 1, rows


async def _developmentaid_session_harvest(
    listing_url: str, max_pages: int
) -> tuple[str, list[str], str, int, list[dict]]:
    return await asyncio.to_thread(_developmentaid_session_harvest_sync, listing_url, max_pages)


def _reportertenders_harvest_sync(
    listing_url: str,
    max_pages: int,
) -> tuple[str, list[str], str, int, list[dict]]:
    _ = max_pages
    req = Request(
        listing_url,
        headers={
            "User-Agent": settings.DEVELOPMENTAID_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urlopen(req, timeout=45) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    rows = _reportertenders_rows_from_html(html, listing_url)
    if not rows:
        raise RuntimeError("ReporterTenders parser found no /bids/ listing links.")
    markdown = _rows_to_listing_markdown("ReporterTenders listings", listing_url, rows)
    links = [str(row.get("detail_url")) for row in rows if row.get("detail_url")]
    return markdown, list(dict.fromkeys(links)), html, 1, rows


async def _reportertenders_harvest(
    listing_url: str,
    max_pages: int,
) -> tuple[str, list[str], str, int, list[dict]]:
    return await asyncio.to_thread(_reportertenders_harvest_sync, listing_url, max_pages)


def _afdb_rss_fetch_page(page: int | None) -> bytes:
    """Fetch one page of the AfDB procurement RSS feed (page=None → base feed)."""
    rss_url = "https://www.afdb.org/en/projects-and-operations/procurement.xml"
    if page is not None:
        rss_url += f"?page={page}"
    req = Request(
        rss_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            )
        },
    )
    with urlopen(req, timeout=45) as resp:
        return resp.read()


def _afdb_rss_fallback_sync(
    required_country: str | None,
    max_pages: int = 1,
) -> tuple[str, list[str], str, int]:
    """
    Fallback for AfDB procurement when browser capture is empty/challenge-like.
    Uses official RSS feed (paginated via ?page=N) and applies an optional
    country keyword filter. Aggregates and de-duplicates across pages.
    """
    pages = max(_MIN_PAGE_ATTEMPTS, min(int(max_pages or _MIN_PAGE_ATTEMPTS), 6))
    wanted = (required_country or "").strip().lower()

    rows: list[str] = []
    links: list[str] = []
    seen_links: set[str] = set()
    xml_first = ""
    kept = 0

    # page=None is the base feed; subsequent paged URLs use ?page=1..N-1
    page_params: list[int | None] = [None] + list(range(1, pages))
    for idx, page in enumerate(page_params):
        try:
            raw = _afdb_rss_fetch_page(page)
        except Exception as exc:
            logger.warning("AfDB RSS page=%s fetch failed: %s", page, exc)
            continue
        if idx == 0:
            xml_first = raw.decode("utf-8", errors="replace")
        try:
            root = ET.fromstring(raw)
        except Exception as exc:
            logger.warning("AfDB RSS page=%s parse failed: %s", page, exc)
            continue

        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            desc = (item.findtext("description") or "").strip()

            if link and link in seen_links:
                continue

            hay = f"{title}\n{desc}".lower()
            if wanted and wanted not in hay:
                continue

            if link:
                seen_links.add(link)
            kept += 1
            rows.append(f"- {title}\n  - Date: {pub}\n  - Link: {link}")
            if link:
                links.append(link)

    xml_text = xml_first
    body = (
        "AfDB procurement RSS fallback (browser listing unavailable).\n\n"
        f"Filter: {wanted or 'none'}\n"
        f"Pages scanned: {pages}\n"
        f"Matched notices: {kept}\n\n"
        + "\n".join(rows[:300])
    )
    return body, list(dict.fromkeys(links)), xml_text, 1


async def _afdb_rss_fallback(
    required_country: str | None,
    max_pages: int = 1,
) -> tuple[str, list[str], str, int]:
    return await asyncio.to_thread(_afdb_rss_fallback_sync, required_country, max_pages)


def _is_ungm_url(url: str) -> bool:
    """UN Global Marketplace public notice listing."""
    return "ungm.org" in urlparse(url or "").netloc.lower()


async def _capture_ungm_listing(
    page, listing_url: str, max_pages: int
) -> tuple[str, list[str], str, int]:
    """
    UNGM (ungm.org/Public/Notice) uses infinite scroll + AJAX.
    Strategy:
      1. Navigate with networkidle to let the Angular/React SPA boot.
      2. Wait for the results table to appear (or a timeout).
      3. Scroll to the bottom repeatedly — each scroll triggers a new AJAX
         batch of ~25 notices.  Repeat up to *max_pages* times (default 4 ≈ 100
         notices).
      4. Capture all visible text and links.
    """
    navigated = False
    last_exc: Exception | None = None
    for wait_state in ("networkidle", "domcontentloaded", "commit"):
        try:
            timeout_ms = 60_000 if wait_state == "networkidle" else 45_000
            await _goto_with_retry(page, listing_url, wait_until=wait_state, timeout=timeout_ms)
            navigated = True
            break
        except Exception as exc:
            last_exc = exc
            logger.info("UNGM goto(%s) failed (%s); trying next wait state.", wait_state, exc)
    if not navigated:
        logger.warning("UNGM page failed to load: %s", last_exc)
        return "", [], "", 0
    await page.wait_for_timeout(2_000)

    # Wait for at least one notice row to appear
    try:
        await page.wait_for_selector(
            "table tr td, .notice-row, [class*='notice'], [class*='procurement']",
            timeout=15_000,
        )
    except Exception:
        await page.wait_for_timeout(4_000)

    # Scroll loop — each scroll triggers the next AJAX page
    prev_height = -1
    scrolls_done = 0
    for _ in range(max_pages):
        curr_height: int = await page.evaluate("() => document.body.scrollHeight")
        if curr_height == prev_height:
            break  # no new content loaded
        prev_height = curr_height
        await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        # Give AJAX time to fetch and render the next batch
        await page.wait_for_timeout(2_500)
        scrolls_done += 1

    # Scroll back to top so all content is in the DOM snapshot
    await page.evaluate("() => window.scrollTo(0, 0)")
    await page.wait_for_timeout(300)

    body, page_links, _md, _url = await _capture_visible_listing_page(page, 1)
    html = await page.content()

    logger.info(
        "UNGM harvest: scrolls=%d chars=%d links=%d",
        scrolls_done, len(body), len(page_links),
    )
    return body, page_links, html, scrolls_done or 1


def _is_eu_tenders_portal(url: str) -> bool:
    """True for the EU Funding & Tenders Portal SPA (ec.europa.eu/info/funding-tenders/...)."""
    parsed = urlparse(url or "")
    return parsed.netloc.lower() in ("ec.europa.eu", "www.ec.europa.eu") and "funding-tenders" in parsed.path


_EGP_BIDS_HOSTS = {
    "egp.gov.et",
    "www.egp.gov.et",
    "production.egp.gov.et",
    "www.production.egp.gov.et",
}


def _is_egp_bids_url(url: str) -> bool:
    """Ethiopian eGP public bids listing (including production host)."""
    parsed = urlparse(url or "")
    return parsed.netloc.lower() in _EGP_BIDS_HOSTS and "/egp/bids" in parsed.path.lower()


def _is_2merkato_tenders_url(url: str) -> bool:
    """2merkato tender listing pages are JS-rendered and need DOM waits."""
    parsed = urlparse(url or "")
    return parsed.netloc.lower() == "tender.2merkato.com" and parsed.path.lower().startswith("/tenders")


def _looks_like_2merkato_detail_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    if parsed.netloc.lower() != "tender.2merkato.com":
        return False
    # Example detail path: /tenders/6a70a7390a538a7800000001
    # Detail records are hex-like IDs; exclude listing routes such as /tenders/proforma.
    return bool(re.match(r"^/tenders/[0-9a-f]{12,}$", parsed.path.lower()))


def _two_merkato_page_urls(listing_url: str, max_pages: int) -> list[str]:
    parsed = urlparse(listing_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    pages_budget = max(_MIN_PAGE_ATTEMPTS, min(int(max_pages or _MIN_PAGE_ATTEMPTS), 4))
    try:
        start_page = int((params.get("page") or ["1"])[0] or "1")
    except (TypeError, ValueError):
        start_page = 1

    if "page" not in params:
        params["page"] = [str(start_page)]

    urls: list[str] = []
    for page_num in range(start_page, start_page + pages_budget):
        p = {k: v[0] for k, v in params.items()}
        p["page"] = str(page_num)
        urls.append(
            urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    urlencode(p),
                    parsed.fragment,
                )
            )
        )
    return urls


async def _capture_2merkato_listing(
    page, listing_url: str, max_pages: int
) -> tuple[str, list[str], str, int]:
    """
    2merkato renders the listing client-side; generic immediate capture grabs only
    the shell. Wait for rendered tender links and capture page text + detail URLs.
    """
    page_urls = _two_merkato_page_urls(listing_url, max_pages)
    parts: list[str] = []
    html_parts: list[str] = []
    detail_links: list[str] = []
    seen_detail: set[str] = set()
    pages_captured = 0

    for idx, page_url in enumerate(page_urls, start=1):
        navigated = False
        for wait_state in ("networkidle", "domcontentloaded", "commit"):
            try:
                timeout_ms = 60_000 if wait_state == "networkidle" else 45_000
                await _goto_with_retry(page, page_url, wait_until=wait_state, timeout=timeout_ms)
                navigated = True
                break
            except Exception as exc:
                logger.info(
                    "2merkato goto(%s) failed for page %s (%s); trying next wait state.",
                    wait_state,
                    idx,
                    exc,
                )
        if not navigated:
            logger.warning("2merkato page %s unreachable; stopping pagination.", idx)
            break

        # Let Vue/SPA finish rendering tender cards.
        await page.wait_for_timeout(2500)
        try:
            await page.wait_for_selector('a[href*="/tenders/"]', timeout=20_000)
        except Exception:
            await page.wait_for_timeout(4000)
        await page.wait_for_timeout(1000)

        page_text = await _visible_page_text(page)
        rows = await page.evaluate(
            """() => Array.from(document.querySelectorAll('a[href*="/tenders/"]'))
                .map((a) => {
                    const href = a.href || '';
                    const text = (a.innerText || a.textContent || '')
                        .replace(/\\s+/g, ' ')
                        .trim();
                    return { href, text };
                })
                .filter((item) => item.href)"""
        )

        page_detail_lines: list[str] = []
        for row in rows or []:
            href = str(row.get("href") or "").strip()
            text = str(row.get("text") or "").strip()
            if not _looks_like_2merkato_detail_url(href):
                continue
            if href not in seen_detail:
                seen_detail.add(href)
                detail_links.append(href)
            label = text if text else href.rsplit("/", 1)[-1]
            page_detail_lines.append(f"- [{label}]({href.replace(')', '%29')})")

        if page_text.strip() or page_detail_lines:
            section = f"\n\n--- Page {idx}: {page.url} ---\n\n{page_text}"
            if page_detail_lines:
                section += "\n\nVisible tender links:\n" + "\n".join(
                    list(dict.fromkeys(page_detail_lines))
                )
            parts.append(section)
            pages_captured += 1

        html_parts.append(await page.content())

        # No rendered tender links on this page usually means pagination is exhausted.
        if not page_detail_lines:
            break

    return (
        "\n".join(parts).strip(),
        detail_links,
        "\n".join(html_parts),
        pages_captured,
    )


async def _egp_click_if_visible(page, selector: str) -> bool:
    try:
        locator = page.locator(selector).first
        if await locator.count() == 0:
            return False
        if not await locator.is_visible():
            return False
        await locator.click()
        await page.wait_for_timeout(1000)
        return True
    except Exception:
        return False


async def _capture_egp_bids_listing(
    page, listing_url: str, max_pages: int
) -> tuple[str, list[str], str, int]:
    """
    eGP renders listings dynamically; rely on robust waits and row extraction
    instead of generic pagination selectors.
    """
    navigated = False
    last_exc: Exception | None = None
    for wait_state in ("domcontentloaded", "networkidle", "commit"):
        try:
            timeout_ms = 70_000 if wait_state == "networkidle" else 45_000
            await _goto_with_retry(page, listing_url, wait_until=wait_state, timeout=timeout_ms)
            navigated = True
            break
        except Exception as exc:
            last_exc = exc
            logger.info("EGP goto(%s) failed (%s); trying next wait state.", wait_state, exc)
    if not navigated:
        logger.warning("EGP page failed to load: %s", last_exc)
        return "", [], "", 0

    # The listing can appear under different tab states. Try to enforce
    # "All Tenders" and "Table" where available.
    await _egp_click_if_visible(page, 'button:has-text("All Tenders")')
    await _egp_click_if_visible(page, 'a:has-text("All Tenders")')
    await _egp_click_if_visible(page, 'button:has-text("Table")')
    await _egp_click_if_visible(page, 'a:has-text("Table")')

    # Give XHR-backed grid enough time to populate.
    await page.wait_for_timeout(3500)
    try:
        await page.wait_for_selector(
            "table tbody tr, .table tbody tr, .ant-table-tbody tr, [role='row']",
            timeout=20_000,
        )
    except Exception:
        await page.wait_for_timeout(5000)

    pages_budget = max(_MIN_PAGE_ATTEMPTS, min(max_pages or _MIN_PAGE_ATTEMPTS, 4))
    seen_rows: set[str] = set()
    out_rows: list[str] = []
    seen_api_rows: set[str] = set()
    api_rows: list[str] = []
    api_links: list[str] = []
    api_hits: list[str] = []
    pages_captured = 0

    def _row_text_from_payload_item(item: dict) -> tuple[str | None, str | None]:
        ref = str(
            item.get("procurement_ref_no")
            or item.get("procurementRefNo")
            or item.get("reference")
            or item.get("tenderNumber")
            or item.get("bidNo")
            or ""
        ).strip()
        lot = str(item.get("lot_no") or item.get("lotNo") or item.get("lot") or "").strip()
        title = str(
            item.get("procurement_title")
            or item.get("procurementTitle")
            or item.get("title")
            or item.get("name")
            or item.get("description")
            or ""
        ).strip()
        entity = str(
            item.get("procuring_entity")
            or item.get("procuringEntity")
            or item.get("entity")
            or item.get("buyer")
            or ""
        ).strip()
        category = str(item.get("procurement_category") or item.get("category") or "").strip()
        market = str(item.get("market_approach") or item.get("marketApproach") or "").strip()
        source = str(item.get("source") or "").strip()
        deadline = str(
            item.get("submission_deadline")
            or item.get("submissionDeadline")
            or item.get("deadline")
            or item.get("closingDate")
            or ""
        ).strip()
        detail_url = str(
            item.get("detail_url")
            or item.get("detailUrl")
            or item.get("url")
            or item.get("link")
            or ""
        ).strip()

        if not title and not ref:
            return None, None

        parts = [part for part in (ref, f"Lot: {lot}" if lot else "", title, entity, category, market, source, deadline) if part]
        row = " | ".join(parts).strip()
        if not row:
            return None, detail_url or None
        return row, (detail_url or None)

    def _row_text_from_sequence(values: list[object]) -> str | None:
        parts: list[str] = []
        for val in values:
            if val is None:
                continue
            text = str(val).strip()
            if not text:
                continue
            parts.append(" ".join(text.split()))
        if len(parts) < 3:
            return None
        row = " | ".join(parts)
        if len(row) < 25:
            return None
        return row

    def _collect_rows_from_payload(payload: object) -> None:
        stack: list[object] = [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                # Process likely row-like records directly.
                row_text, detail_link = _row_text_from_payload_item(node)
                if row_text and row_text not in seen_api_rows:
                    seen_api_rows.add(row_text)
                    api_rows.append(row_text)
                if detail_link and detail_link not in api_links and detail_link.startswith("http"):
                    api_links.append(detail_link)

                for value in node.values():
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(node, list):
                # Some grids return rows as arrays instead of keyed dicts.
                if node and all(not isinstance(x, (dict, list)) for x in node):
                    row_text = _row_text_from_sequence(node)
                    if row_text and row_text not in seen_api_rows:
                        seen_api_rows.add(row_text)
                        api_rows.append(row_text)
                for item in node:
                    if isinstance(item, (dict, list)):
                        stack.append(item)

    def _collect_rows_from_html_fragment(fragment: str) -> None:
        try:
            soup = BeautifulSoup(fragment, "html.parser")
        except Exception:
            return
        for tr in soup.select("table tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.select("th,td")]
            row_text = _row_text_from_sequence(cells)
            if row_text and row_text not in seen_api_rows:
                seen_api_rows.add(row_text)
                api_rows.append(row_text)

    async def _capture_response_payload(resp) -> None:
        try:
            u = (resp.url or "").strip()
            ul = u.lower()
            status = int(resp.status or 0)
            if status < 200 or status >= 400:
                return
            if not any(token in ul for token in ("bid", "tender", "procurement", "/api/")):
                return
            if u not in api_hits:
                api_hits.append(u)

            ctype = (resp.headers or {}).get("content-type", "").lower()
            if "json" in ctype:
                try:
                    _collect_rows_from_payload(await resp.json())
                    return
                except Exception:
                    pass

            raw = await resp.text()
            if not raw:
                return

            # JSON-like payload served with wrong content-type.
            trimmed = raw.strip()
            if trimmed[:1] in ("{", "["):
                try:
                    _collect_rows_from_payload(json.loads(trimmed))
                    return
                except Exception:
                    pass

            # HTML fragment/table payload fallback.
            if "<table" in raw.lower() or "<tr" in raw.lower():
                _collect_rows_from_html_fragment(raw)
        except Exception:
            return

    def _on_response(resp) -> None:
        asyncio.create_task(_capture_response_payload(resp))

    page.on("response", _on_response)

    for page_idx in range(1, pages_budget + 1):
        rows = await page.evaluate(
            """() => {
                const selectors = [
                    'table tbody tr',
                    '.table tbody tr',
                    '.ant-table-tbody tr',
                    '[role="row"]',
                ];
                const allRows = [];
                for (const sel of selectors) {
                    for (const tr of document.querySelectorAll(sel)) {
                        const txt = (tr.innerText || tr.textContent || '')
                            .replace(/\\s+/g, ' ')
                            .trim();
                        if (txt && txt.length >= 25) allRows.push(txt);
                    }
                }
                return allRows;
            }"""
        )
        for row in rows or []:
            line = str(row).strip()
            if not line or line in seen_rows:
                continue
            seen_rows.add(line)
            out_rows.append(line)
        pages_captured += 1

        # Try to navigate to next page using common controls used by data grids.
        if page_idx >= pages_budget:
            break
        moved = await page.evaluate(
            """() => {
                const candidates = Array.from(
                    document.querySelectorAll('button, a, li, [role="button"]')
                );
                const next = candidates.find((el) => {
                    const txt = (el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (!txt) return false;
                    return txt === 'next' || txt === '>' || txt === '›' || txt.includes('next');
                });
                if (!next) return false;
                const attr = ((next.getAttribute('class') || '') + ' ' + (next.getAttribute('aria-disabled') || '')).toLowerCase();
                if (attr.includes('disabled') || attr.includes('true')) return false;
                next.click();
                return true;
            }"""
        )
        if not moved:
            break
        await page.wait_for_timeout(2200)

    page_text = await _visible_page_text(page)
    page_links = await _visible_links(page)
    # Allow in-flight JSON handlers to complete.
    await page.wait_for_timeout(600)
    if not out_rows and api_rows:
        out_rows.extend(api_rows[:500])
    if api_links:
        page_links.extend(api_links)
    html = await page.content()

    rows_md = "\n".join(f"- {row}" for row in out_rows[:400])
    if out_rows:
        logger.info("EGP extracted rows=%s links=%s api_hits=%s", len(out_rows), len(page_links), len(api_hits))
    else:
        low = page_text.lower()
        blocked = (
            "inspect is not allowed" in low
            or "developer tools are not permitted" in low
            or "close devtools" in low
        )
        logger.warning(
            "EGP returned no rows (chars=%s links=%s blocked=%s api_hits=%s urls=%s)",
            len(page_text),
            len(page_links),
            blocked,
            len(api_hits),
            api_hits[:5],
        )
    body = (
        f"\n\n--- EGP Listing: {page.url} ---\n\n"
        f"{page_text}\n\n"
        "Visible tender rows:\n"
        f"{rows_md}"
    ).strip()
    return body, page_links, html, pages_captured


def _eu_portal_page_urls(listing_url: str, max_pages: int) -> list[str]:
    """
    Generate up to *max_pages* paginated URLs for the EU portal by incrementing
    the `pageNumber` query parameter.  Returns the original URL unchanged when
    `pageNumber` is absent.
    """
    parsed = urlparse(listing_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    pages_budget = max(_MIN_PAGE_ATTEMPTS, int(max_pages or _MIN_PAGE_ATTEMPTS))
    try:
        start_page = int((params.get("pageNumber") or ["1"])[0] or "1")
    except (TypeError, ValueError):
        start_page = 1

    if "pageNumber" not in params:
        params["pageNumber"] = [str(start_page)]
    urls: list[str] = []
    for page_num in range(start_page, start_page + pages_budget):
        p = {k: v[0] for k, v in params.items()}
        p["pageNumber"] = str(page_num)
        new_url = urlunparse((
            parsed.scheme, parsed.netloc, parsed.path,
            parsed.params, urlencode(p), parsed.fragment,
        ))
        urls.append(new_url)
    return urls


async def _accept_eu_cookie_consent(page) -> None:
    """Dismiss the EU cookie consent banner so the React SPA can fully render."""
    for selector in (
        'button:has-text("Accept only essential cookies")',
        'button:has-text("Accept all cookies")',
        'button[id*="cookie"]:has-text("Accept")',
        '[data-testid="cookie-consent-accept"]',
    ):
        try:
            locator = page.locator(selector).first
            if await locator.count() > 0 and await locator.is_visible():
                await locator.click()
                await page.wait_for_timeout(1500)
                return
        except Exception:
            pass


async def _capture_eu_portal_listing(
    page, listing_url: str, max_pages: int
) -> tuple[str, list[str], str, int]:
    """
    EU Funding & Tenders Portal is a React SPA that does constant background
    polling, so `networkidle` and `load` rarely resolve.  Use `domcontentloaded`
    and then wait for a results selector to appear.  Accept the cookie consent
    on the first visit, then harvest visible text and links.
    """
    page_urls = _eu_portal_page_urls(listing_url, max_pages)
    parts: list[str] = []
    all_links: list[str] = []
    html_parts: list[str] = []
    pages_captured = 0

    for idx, page_url in enumerate(page_urls, start=1):
        navigated = False
        for wait_state in ("domcontentloaded", "commit"):
            try:
                await _goto_with_retry(page, page_url, wait_until=wait_state, timeout=45_000)
                navigated = True
                break
            except Exception as exc:
                logger.info("EU portal goto(%s) failed (%s); trying next wait state.", wait_state, exc)
        if not navigated:
            logger.warning("EU portal page %d unreachable; stopping pagination.", idx)
            break

        if idx == 1:
            await _accept_eu_cookie_consent(page)

        # Wait for results to appear in the SPA. The portal renders rows inside
        # eui-card / sedia-result-card / .opportunity-card-info elements.
        try:
            await page.wait_for_selector(
                'eui-card, sedia-result-card, [class*="result-card"], [class*="opportunity"]',
                timeout=20_000,
            )
        except Exception:
            await page.wait_for_timeout(6_000)

        # Small extra settle so trailing rows render.
        await page.wait_for_timeout(1_500)

        body, page_links, _md, _url = await _capture_visible_listing_page(page, idx)

        if not body.strip():
            await page.wait_for_timeout(3_000)
            body, page_links, _md, _url = await _capture_visible_listing_page(page, idx)

        if not body.strip():
            logger.warning("EU portal page %d returned no content; stopping pagination.", idx)
            break

        parts.append(body)
        all_links.extend(page_links)
        html_parts.append(await page.content())
        pages_captured += 1

    return (
        "\n".join(parts).strip(),
        list(dict.fromkeys(all_links)),
        "\n".join(html_parts),
        pages_captured,
    )


async def _visible_page_text(page) -> str:
    try:
        return (await page.locator("body").inner_text()).strip()
    except Exception:
        html = await page.content()
        return _html_to_text(html)


async def _visible_links(page) -> list[str]:
    links = await page.evaluate(
        """() => Array.from(document.querySelectorAll('a[href]'))
            .filter((a) => {
                let el = a;
                while (el) {
                    const style = window.getComputedStyle(el);
                    if (
                        style.display === 'none' ||
                        style.visibility === 'hidden' ||
                        style.opacity === '0'
                    ) return false;
                    el = el.parentElement;
                }
                const rect = a.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            })
            .map((a) => a.href)
            .filter(Boolean)"""
    )
    return list(dict.fromkeys(str(link) for link in links if str(link).startswith("http")))


async def _visible_markdown_links(page) -> str:
    rows = await page.evaluate(
        """() => Array.from(document.querySelectorAll('a[href]'))
            .filter((a) => {
                let el = a;
                while (el) {
                    const style = window.getComputedStyle(el);
                    if (
                        style.display === 'none' ||
                        style.visibility === 'hidden' ||
                        style.opacity === '0'
                    ) return false;
                    el = el.parentElement;
                }
                const rect = a.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            })
            .map((a) => {
                const text = (a.innerText || a.textContent || '').replace(/\\s+/g, ' ').trim();
                return { text, href: a.href };
            })
            .filter((item) => item.text && item.href)"""
    )

    lines: list[str] = []
    seen: set[str] = set()
    for row in rows:
        href = str(row.get("href") or "").strip()
        text = str(row.get("text") or "").strip()
        if not href.startswith("http") or not text:
            continue
        key = f"{text}|{href}"
        if key in seen:
            continue
        seen.add(key)
        safe_text = text.replace("[", "(").replace("]", ")")
        safe_href = href.replace(")", "%29")
        lines.append(f"- [{safe_text}]({safe_href})")
    return "\n".join(lines)


async def _capture_visible_listing_page(page, page_number: int) -> tuple[str, list[str], str, str]:
    page_text = await _visible_page_text(page)
    page_links = await _visible_links(page)
    md_links = await _visible_markdown_links(page)
    url = page.url
    body = f"\n\n--- Page {page_number}: {url} ---\n\n{page_text}"
    if md_links:
        body = f"{body}\n\nVisible notice/detail links:\n{md_links}"
    return body, page_links, md_links, url


async def _find_next_pagination_locator(page):
    selectors = (
        'a[rel="next"]',
        'link[rel="next"]',
        '.pager__item--next a',
        '.pager-next a',
        '.pagination-next a',
        'li.next a',
        'a[aria-label="Next"]',
        'button[aria-label="Next"]',
        'a:has-text("Next")',
        'button:has-text("Next")',
        'a:has-text("›")',
        'a:has-text("»")',
    )
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.count() == 0:
                continue
            if selector.startswith("link["):
                href = await locator.get_attribute("href")
                if href:
                    return ("goto", urljoin(page.url, href))
                continue
            if not await locator.is_visible():
                continue
            disabled = await locator.evaluate(
                """(el) => {
                    const cls = (el.getAttribute('class') || '').toLowerCase();
                    const aria = (el.getAttribute('aria-disabled') || '').toLowerCase();
                    return el.disabled === true || aria === 'true' || cls.includes('disabled');
                }"""
            )
            if not disabled:
                return ("click", locator)
        except Exception:
            continue
    return None


async def _capture_paginated_listing(page, listing_url: str, wait_until: str) -> tuple[str, list[str], str, int]:
    max_pages = _max_pages_for_listing_url(listing_url)
    parts: list[str] = []
    all_links: list[str] = []
    html_parts: list[str] = []
    seen_urls: set[str] = set()
    pages_captured = 0

    for page_number in range(1, max_pages + 1):
        current_url = page.url
        if current_url in seen_urls:
            break
        seen_urls.add(current_url)

        body, page_links, _md_links, _url = await _capture_visible_listing_page(page, page_number)
        parts.append(body)
        all_links.extend(page_links)
        html_parts.append(await page.content())
        pages_captured += 1

        if page_number >= max_pages:
            break

        next_target = await _find_next_pagination_locator(page)
        if not next_target:
            break

        before = page.url
        try:
            mode, target = next_target
            if mode == "goto":
                await _goto_with_retry(page, target, wait_until=wait_until)
            else:
                await target.click()
                await page.wait_for_load_state(wait_until)
            await page.wait_for_timeout(500)
        except Exception as exc:
            logger.info("Pagination stopped for %s: %s", listing_url, exc)
            break
        if page.url == before:
            break

    return "\n".join(parts).strip(), list(dict.fromkeys(all_links)), "\n".join(html_parts), pages_captured


def _resolve_auth_selectors(monitored: MonitoredPage) -> dict[str, str]:
    data: dict[str, str] = {
        "username": settings.PLAYWRIGHT_AUTH_USER_SELECTOR,
        "password": settings.PLAYWRIGHT_AUTH_PASSWORD_SELECTOR,
        "submit": settings.PLAYWRIGHT_AUTH_SUBMIT_SELECTOR,
    }
    raw = getattr(monitored, "auth_form_selectors_json", None)
    if not raw:
        return data
    try:
        overrides = json.loads(raw)
        if isinstance(overrides, dict):
            for key in ("username", "password", "submit"):
                if overrides.get(key):
                    data[key] = str(overrides[key])
    except json.JSONDecodeError as e:
        logger.warning(
            "Invalid auth_form_selectors_json for page_id=%s: %s",
            getattr(monitored, "id", None),
            e,
        )
    return data


def _read_auth_secret(env_name: str | None) -> str:
    """
    Resolve auth secrets from process env first, then settings-backed .env values.

    This keeps backward compatibility with exported env vars while allowing users
    to store CRAWL_AUTH_USERNAME/CRAWL_AUTH_PASSWORD in local `.env`.
    """
    key = str(env_name or "").strip()
    if not key:
        return ""
    val = os.environ.get(key) or ""
    if val.strip():
        return val
    if key == "CRAWL_AUTH_USERNAME":
        return str(getattr(settings, "CRAWL_AUTH_USERNAME", "") or "")
    if key == "CRAWL_AUTH_PASSWORD":
        return str(getattr(settings, "CRAWL_AUTH_PASSWORD", "") or "")
    return ""


async def _harvest_with_playwright_async(monitored: MonitoredPage) -> HarvestResult:
    """Browser work only (Playwright async). See `harvest_with_playwright` for entry."""
    listing_url = monitored.url
    max_p = _max_pages_for_listing_url(listing_url)
    wb_scope = _worldbank_scope_filter_value(listing_url)
    if _is_worldbank_procurement_url(listing_url) and wb_scope:
        try:
            text, links, raw_json, pages_captured, structured_rows, prefilter_stats = (
                await _worldbank_api_harvest(wb_scope, max_p)
            )
            logger.info(
                "World Bank API harvest scope=%s kept=%s dropped=%s links=%s pages=%s",
                wb_scope,
                prefilter_stats.get("prefilter_kept", 0),
                prefilter_stats.get("prefilter_dropped", 0),
                len(links),
                pages_captured,
            )
            return HarvestResult(
                status="success",
                page_url=listing_url,
                markdown=text,
                html=raw_json,
                listing_urls=links,
                detail_urls=links,
                session_meta={
                    "strategy": "playwright",
                    "backend": "worldbank_procnotices_api",
                    "structured_source": True,
                    "char_count": len(text),
                    "link_count": len(links),
                    "applied_filter": f"wb_api:{wb_scope}",
                    "pages_captured": pages_captured,
                    "max_pages": max_p,
                    "prefilter_stats": prefilter_stats,
                    "listing_rows_v1": structured_rows,
                    "raw_count": prefilter_stats.get("prefilter_kept", 0),
                },
            )
        except Exception as exc:
            logger.exception(
                "World Bank API harvest failed for page_id=%s scope=%s",
                getattr(monitored, "id", None),
                wb_scope,
            )
            return HarvestResult(
                status="failed",
                page_url=listing_url,
                error=f"World Bank API harvest failed: {exc}",
                session_meta={
                    "strategy": "playwright",
                    "backend": "worldbank_procnotices_api",
                    "applied_filter": f"wb_api:{wb_scope}",
                },
            )

    if _is_ethiojobs_consultancy_url(listing_url):
        try:
            text, links, raw_html, pages_captured, structured_rows = await _ethiojobs_harvest(
                listing_url,
                max_p,
            )
            return HarvestResult(
                status="success",
                page_url=listing_url,
                markdown=text,
                html=raw_html,
                listing_urls=links,
                detail_urls=links,
                session_meta={
                    "strategy": "playwright",
                    "backend": "ethiojobs_next_data",
                    "structured_source": True,
                    "char_count": len(text),
                    "link_count": len(links),
                    "pages_captured": pages_captured,
                    "max_pages": max_p,
                    "listing_rows_v1": structured_rows,
                    "raw_count": len(structured_rows),
                },
            )
        except Exception as exc:
            logger.warning("Ethiojobs pre-harvest failed for %s: %s", listing_url, exc)

    if _is_reportertenders_listing_url(listing_url):
        try:
            text, links, raw_html, pages_captured, structured_rows = await _reportertenders_harvest(
                listing_url,
                max_p,
            )
            return HarvestResult(
                status="success",
                page_url=listing_url,
                markdown=text,
                html=raw_html,
                listing_urls=links,
                detail_urls=links,
                session_meta={
                    "strategy": "playwright",
                    "backend": "reportertenders_html",
                    "structured_source": True,
                    "char_count": len(text),
                    "link_count": len(links),
                    "pages_captured": pages_captured,
                    "max_pages": max_p,
                    "listing_rows_v1": structured_rows,
                    "raw_count": len(structured_rows),
                },
            )
        except Exception as exc:
            logger.warning("ReporterTenders pre-harvest failed for %s: %s", listing_url, exc)

    pre_harvest_error: str | None = None
    if _is_developmentaid_tenders_url(listing_url):
        try:
            text, links, raw_html, pages_captured, structured_rows = await _developmentaid_session_harvest(
                listing_url,
                max_p,
            )
            return HarvestResult(
                status="success",
                page_url=listing_url,
                markdown=text,
                html=raw_html,
                listing_urls=links,
                detail_urls=links,
                session_meta={
                    "strategy": "playwright",
                    "backend": "developmentaid_session",
                    "structured_source": True,
                    "char_count": len(text),
                    "link_count": len(links),
                    "pages_captured": pages_captured,
                    "max_pages": max_p,
                    "listing_rows_v1": structured_rows,
                    "raw_count": len(structured_rows),
                },
            )
        except Exception as exc:
            pre_harvest_error = str(exc)
            logger.warning(
                "DevelopmentAid session pre-harvest failed for %s: %s; continuing with browser fallback.",
                listing_url,
                exc,
            )

    nav_url = _afdb_navigation_url(listing_url)
    login_url = _resolve_login_url_for_page(monitored, listing_url)
    devaid_cookie = str(getattr(settings, "DEVELOPMENTAID_SESSION_COOKIE", "") or "").strip()
    if _is_developmentaid_tenders_url(listing_url) and devaid_cookie:
        # For DevelopmentAid, prefer session-cookie auth over form login.
        # Login page is often challenge-protected and not reliably automatable.
        login_url = None
    user_env = getattr(monitored, "auth_username_env", None) or settings.PLAYWRIGHT_AUTH_USERNAME_ENV
    pass_env = getattr(monitored, "auth_password_env", None) or settings.PLAYWRIGHT_AUTH_PASSWORD_ENV

    from playwright.async_api import async_playwright

    selectors = _resolve_auth_selectors(monitored)
    wait_until = settings.PLAYWRIGHT_GOTO_WAIT or "load"
    if wait_until not in ("load", "domcontentloaded", "networkidle", "commit"):
        wait_until = "load"

    html = ""
    text = ""
    links: list[str] = []
    applied_filter = None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=settings.PLAYWRIGHT_HEADLESS,
                slow_mo=settings.PLAYWRIGHT_SLOW_MO_MS or 0,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            try:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                    timezone_id="Africa/Addis_Ababa",
                    viewport={"width": 1366, "height": 768},
                    extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
                )
                await context.add_init_script(
                    """
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
                    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                    window.chrome = window.chrome || { runtime: {} };
                    """
                )
                page = await context.new_page()
                page.set_default_timeout(settings.PLAYWRIGHT_TIMEOUT_MS)

                if login_url:
                    username = _read_auth_secret(user_env)
                    password = _read_auth_secret(pass_env)

                    await _goto_with_retry(page, login_url, wait_until=wait_until)
                    await page.locator(selectors["username"]).first.fill(username)
                    await page.locator(selectors["password"]).first.fill(password)
                    await page.locator(selectors["submit"]).first.click()
                    await page.wait_for_load_state(wait_until)

                if _is_ungm_url(listing_url):
                    # UNGM handler does its own goto with networkidle/load fallback.
                    text, links, html, pages_captured = await _capture_ungm_listing(
                        page, listing_url, max_p
                    )
                elif _is_eu_tenders_portal(listing_url):
                    # EU portal handler does its own goto with domcontentloaded.
                    # The "load" event never fires on this SPA so pre-navigation
                    # would just time out for 90s.
                    text, links, html, pages_captured = await _capture_eu_portal_listing(
                        page, listing_url, max_p
                    )
                elif _is_egp_bids_url(listing_url):
                    text, links, html, pages_captured = await _capture_egp_bids_listing(
                        page, listing_url, max_p
                    )
                elif _is_2merkato_tenders_url(listing_url):
                    text, links, html, pages_captured = await _capture_2merkato_listing(
                        page, listing_url, max_p
                    )
                else:
                    # Generic listing — try the configured wait state first,
                    # then fall back to domcontentloaded for sites that never
                    # fire the "load" event.
                    try:
                        await _goto_with_retry(page, nav_url, wait_until=wait_until, timeout=45_000)
                    except Exception as goto_exc:
                        logger.info(
                            "Listing goto(%s) failed (%s); retrying with domcontentloaded.",
                            wait_until, goto_exc,
                        )
                        await _goto_with_retry(page, nav_url, wait_until="domcontentloaded", timeout=45_000)

                    applied_filter = await _apply_undp_region_filter(page, listing_url)
                    if not applied_filter:
                        afdb_country = await _apply_afdb_country_filter(page, listing_url)
                        if afdb_country:
                            applied_filter = f"afdb_country:{afdb_country}"
                    if not applied_filter:
                        wb_scope = await _apply_worldbank_region_filter(page, listing_url)
                        if wb_scope:
                            applied_filter = f"wb_scope:{wb_scope}"
                    text, links, html, pages_captured = await _capture_paginated_listing(
                        page,
                        listing_url,
                        wait_until,
                    )

                    # AfDB can intermittently return Cloudflare challenge shells in
                    # automation contexts. If capture is too small/challenge-like,
                    # fall back to the official RSS feed.
                    if _is_afdb_procurement_url(listing_url):
                        country_hint = _afdb_country_filter_value(listing_url)
                        if len((text or "").strip()) < 1200 or _looks_like_cloudflare_challenge(text, html):
                            rss_pages = _max_pages_for_listing_url(listing_url)
                            logger.warning(
                                "AfDB browser capture looked incomplete/challenge-like; using RSS fallback (country=%s, pages=%s)",
                                country_hint or "none", rss_pages,
                            )
                            text, links, html, pages_captured = await _afdb_rss_fallback(
                                country_hint, rss_pages
                            )
                            if country_hint:
                                applied_filter = f"afdb_country:{country_hint} (rss_fallback)"
            finally:
                await browser.close()
    except Exception as e:
        logger.exception("Playwright harvest failed for page_id=%s", getattr(monitored, "id", None))
        err = str(e)
        if pre_harvest_error:
            err = f"{err} | pre-harvest: {pre_harvest_error}"
        return HarvestResult(
            status="failed",
            page_url=listing_url,
            error=err,
            session_meta={"strategy": "playwright"},
        )

    if not text:
        text = _html_to_text(html)
    if not links:
        links = _extract_links(html, listing_url)
    if _looks_like_cloudflare_challenge(text, html) and _links_look_like_challenge_artifacts(links):
        err = "Cloudflare challenge page captured instead of listing content."
        if pre_harvest_error:
            err = f"{err} pre-harvest: {pre_harvest_error}"
        return HarvestResult(
            status="failed",
            page_url=listing_url,
            error=err,
            session_meta={"strategy": "playwright", "challenge_page": True},
        )
    return HarvestResult(
        status="success",
        page_url=listing_url,
        markdown=text,
        html=html,
        listing_urls=links,
        session_meta={
            "strategy": "playwright",
            "char_count": len(text),
            "link_count": len(links),
            "applied_filter": applied_filter,
            "pages_captured": pages_captured,
            "max_pages": _max_pages_for_listing_url(listing_url),
        },
    )


async def harvest_with_playwright(monitored: MonitoredPage) -> HarvestResult:
    """
    Log in (if auth_login_url + env credentials resolve), then navigate to monitored.url
    and return page HTML as plain text + link hrefs for Agent1.
    """
    from app.core.playwright_windows_async import (
        needs_windows_playwright_thread,
        run_coro_on_windows_playwright_loop,
    )

    listing_url = monitored.url
    login_url = _resolve_login_url_for_page(monitored, listing_url)
    devaid_cookie = str(getattr(settings, "DEVELOPMENTAID_SESSION_COOKIE", "") or "").strip()
    if _is_developmentaid_tenders_url(listing_url) and devaid_cookie:
        login_url = None
    user_env = getattr(monitored, "auth_username_env", None) or settings.PLAYWRIGHT_AUTH_USERNAME_ENV
    pass_env = getattr(monitored, "auth_password_env", None) or settings.PLAYWRIGHT_AUTH_PASSWORD_ENV

    if login_url:
        username = _read_auth_secret(user_env)
        password = _read_auth_secret(pass_env)
        if not username.strip() or not password.strip():
            return HarvestResult(
                status="failed",
                page_url=listing_url,
                error=(
                    f"Missing credentials: set {user_env} and {pass_env} in the environment (.env)"
                ),
                session_meta={
                    "strategy": "playwright",
                    "login_url_set": True,
                },
            )

    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError as e:
        return HarvestResult(
            status="failed",
            page_url=listing_url,
            error=f"Playwright not installed: {e}",
            session_meta={"strategy": "playwright"},
        )

    if needs_windows_playwright_thread():
        logger.info(
            "Playwright on Windows: server loop is not Proactor (typical with uvicorn --reload); "
            "running harvest on a worker thread with its own Proactor loop."
        )

        def _run_sync() -> HarvestResult:
            return run_coro_on_windows_playwright_loop(
                _harvest_with_playwright_async(monitored)
            )

        return await asyncio.to_thread(_run_sync)

    return await _harvest_with_playwright_async(monitored)
