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
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from app.core.config import settings
from app.crawl.types import HarvestResult
from app.models.page import MonitoredPage

logger = logging.getLogger(__name__)
_MIN_PAGE_ATTEMPTS = 2


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
            await page.goto(listing_url, wait_until=wait_state, timeout=timeout_ms)
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


def _is_egp_bids_url(url: str) -> bool:
    """Ethiopian eGP public bids listing."""
    parsed = urlparse(url or "")
    return parsed.netloc.lower() in ("egp.gov.et", "www.egp.gov.et") and "/egp/bids" in parsed.path.lower()


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
            await page.goto(listing_url, wait_until=wait_state, timeout=timeout_ms)
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
    pages_captured = 0

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
    html = await page.content()

    rows_md = "\n".join(f"- {row}" for row in out_rows[:400])
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
                await page.goto(page_url, wait_until=wait_state, timeout=45_000)
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
                await page.goto(target, wait_until=wait_until)
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


async def _harvest_with_playwright_async(monitored: MonitoredPage) -> HarvestResult:
    """Browser work only (Playwright async). See `harvest_with_playwright` for entry."""
    listing_url = monitored.url
    nav_url = _afdb_navigation_url(listing_url)
    login_url = getattr(monitored, "auth_login_url", None) or settings.PLAYWRIGHT_AUTH_LOGIN_URL
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
            )
            try:
                context = await browser.new_context()
                await context.add_init_script(
                    """
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    window.chrome = window.chrome || { runtime: {} };
                    """
                )
                page = await context.new_page()
                page.set_default_timeout(settings.PLAYWRIGHT_TIMEOUT_MS)

                if login_url:
                    username = os.environ.get(user_env or "")
                    password = os.environ.get(pass_env or "")

                    await page.goto(login_url, wait_until=wait_until)
                    await page.locator(selectors["username"]).first.fill(username)
                    await page.locator(selectors["password"]).first.fill(password)
                    await page.locator(selectors["submit"]).first.click()
                    await page.wait_for_load_state(wait_until)

                max_p = _max_pages_for_listing_url(listing_url)

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
                else:
                    # Generic listing — try the configured wait state first,
                    # then fall back to domcontentloaded for sites that never
                    # fire the "load" event.
                    try:
                        await page.goto(nav_url, wait_until=wait_until, timeout=45_000)
                    except Exception as goto_exc:
                        logger.info(
                            "Listing goto(%s) failed (%s); retrying with domcontentloaded.",
                            wait_until, goto_exc,
                        )
                        await page.goto(nav_url, wait_until="domcontentloaded", timeout=45_000)

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
        return HarvestResult(
            status="failed",
            page_url=listing_url,
            error=str(e),
            session_meta={"strategy": "playwright"},
        )

    if not text:
        text = _html_to_text(html)
    if not links:
        links = _extract_links(html, listing_url)
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
    login_url = getattr(monitored, "auth_login_url", None) or settings.PLAYWRIGHT_AUTH_LOGIN_URL
    user_env = getattr(monitored, "auth_username_env", None) or settings.PLAYWRIGHT_AUTH_USERNAME_ENV
    pass_env = getattr(monitored, "auth_password_env", None) or settings.PLAYWRIGHT_AUTH_PASSWORD_ENV

    if login_url:
        username = os.environ.get(user_env or "") if user_env else ""
        password = os.environ.get(pass_env or "") if pass_env else ""
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
