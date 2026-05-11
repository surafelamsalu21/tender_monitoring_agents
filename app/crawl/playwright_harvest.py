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
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
from app.core.config import settings
from app.crawl.types import HarvestResult
from app.models.page import MonitoredPage

logger = logging.getLogger(__name__)


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


def _eu_portal_page_urls(listing_url: str, max_pages: int) -> list[str]:
    """
    Generate up to *max_pages* paginated URLs for the EU portal by incrementing
    the `pageNumber` query parameter.  Returns the original URL unchanged when
    `pageNumber` is absent.
    """
    parsed = urlparse(listing_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    if "pageNumber" not in params:
        return [listing_url]
    urls: list[str] = []
    for page_num in range(1, max_pages + 1):
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
    max_pages = max(1, min(int(getattr(settings, "PLAYWRIGHT_MAX_PAGES", 4) or 4), 4))
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

                max_p = max(1, min(int(getattr(settings, "PLAYWRIGHT_MAX_PAGES", 4) or 4), 4))

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
                else:
                    # Generic listing — try the configured wait state first,
                    # then fall back to domcontentloaded for sites that never
                    # fire the "load" event.
                    try:
                        await page.goto(listing_url, wait_until=wait_until, timeout=45_000)
                    except Exception as goto_exc:
                        logger.info(
                            "Listing goto(%s) failed (%s); retrying with domcontentloaded.",
                            wait_until, goto_exc,
                        )
                        await page.goto(
                            listing_url, wait_until="domcontentloaded", timeout=45_000
                        )

                    applied_filter = await _apply_undp_region_filter(page, listing_url)
                    text, links, html, pages_captured = await _capture_paginated_listing(
                        page,
                        listing_url,
                        wait_until,
                    )
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
            "max_pages": max(1, min(int(getattr(settings, "PLAYWRIGHT_MAX_PAGES", 4) or 4), 4)),
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
