#!/usr/bin/env python3
"""
World Bank RFx Now — Playwright smoke: login (from .env) and save post-login page HTML.

Prerequisites:
  pip install playwright python-dotenv
  playwright install chromium

Required .env variables (never commit real values):
  WB_RFX_AUTH_LOGIN_URL   — e.g. https://wbgeprocure-rfxnow.worldbank.org/rfxnow/external/login.html
  WB_RFX_AUTH_USERNAME    — WBGeProcure / RFx username
  WB_RFX_AUTH_PASSWORD

Optional:
  WB_RFX_AUTH_APP_NUMBER — Application Number when WB marks the field required
  WB_RFX_LOGIN_CODE — one-time Login Code from email after password (or use MFA stdin prompt)
  WB_RFX_MFA_STDIN_PROMPT=true — paste code interactively when MFA page appears (terminal)
  PLAYWRIGHT_HEADLESS — default true; set false to watch steps in a real window

Email MFA (second step — same portal, form posts to /external/verify.html):
  After password, WB sends a Login Code email. When the pink notice appears,
  Playwright waits for `#loginCode` and can complete the step via either:
    WB_RFX_LOGIN_CODE=<paste code once>           — non-interactive (rotate after use / do not commit)
    WB_RFX_MFA_STDIN_PROMPT=true                 — prompts in this terminal for the code

Outputs (default ./out/, gitignored recommendation):
  wb_rfx_login_page.html      — DOM snapshot shortly after landing on login URL
  wb_rfx_after_login.html    — DOM after credential + optional MFA submits + wait
  wb_rfx_final.png           — screenshot of final viewport
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def _die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _load_env() -> None:
    env_path = ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()


def _req(name: str) -> str:
    v = os.getenv(name)
    if not v or not str(v).strip():
        _die(f"Missing or empty env var: {name}")
    return str(v).strip()


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _try_fill_application_number(page, value: str) -> None:
    if not value:
        return
    # Third field when label mentions application number — try labelled textbox then generic
    lbl = page.get_by_label(re.compile(r"application", re.I))
    try:
        if lbl.count():
            lbl.first.fill(value)
            return
    except Exception:
        pass


def _fill_wbg_rfx_login_form(page, username: str, password: str, app_no: str) -> None:
    """
    World Bank RFx external login uses form#loginForm with #username, #password,
    #applicationNumber, and #btn-vendor-login. Other password inputs are hidden templates.

    WB often marks Application Number required — set WB_RFX_AUTH_APP_NUMBER in .env when the form rejects blanks.
    """
    form = page.locator("form#loginForm")
    form.scroll_into_view_if_needed()
    user_el = form.locator("#username")
    user_el.wait_for(state="visible")
    user_el.click()
    user_el.fill(username)
    pwd_el = form.locator("#password")
    pwd_el.wait_for(state="visible")
    pwd_el.fill(password)
    if app_no.strip():
        form.locator("#applicationNumber").fill(app_no.strip())
    form.locator("#btn-vendor-login").click()


def _maybe_complete_wbg_rfx_email_login_code(
    page,
    *,
    timeout_ms: int,
    post_submit_ms: int,
) -> None:
    """
    RFx sends an email OTP; markup uses form#loginForm action .../verify.html and #loginCode.
    Same #btn-vendor-login submits the code.
    """
    otp_wait = min(int(os.getenv("WB_RFX_MFA_WAIT_MS", "75000")), timeout_ms)
    code_box = page.locator("#loginCode")
    try:
        code_box.wait_for(state="visible", timeout=otp_wait)
    except Exception:
        return

    print("WB RFx email verification step detected (Login Code field visible).")

    otp = os.getenv("WB_RFX_LOGIN_CODE", "").strip()
    if not otp and _bool_env("WB_RFX_MFA_STDIN_PROMPT", False):
        try:
            otp = input("Paste the Login Code from your email, then Enter: ").strip()
        except EOFError:
            otp = ""

    if not otp:
        print(
            "Skipping OTP submit — set WB_RFX_LOGIN_CODE in .env or "
            "WB_RFX_MFA_STDIN_PROMPT=true for interactive paste.",
            file=sys.stderr,
        )
        return

    code_box.fill(otp)
    page.locator("#btn-vendor-login").click()

    try:
        page.wait_for_load_state(
            "networkidle", timeout=min(post_submit_ms, timeout_ms)
        )
    except Exception:
        page.wait_for_timeout(min(post_submit_ms, timeout_ms))


def _fill_login_generic(page, username: str, password: str, app_no: str, timeout_ms: int) -> None:
    """Fallback when form#loginForm is absent."""
    pwd_input = page.locator('input[type="password"]:visible').first
    pwd_input.wait_for(state="visible", timeout=timeout_ms)
    filled_user = False
    for locator in (
        page.get_by_label(re.compile(r"^\s*username", re.I)),
        page.get_by_placeholder(re.compile(r"username", re.I)),
        page.locator('input[id*="user"]:visible:not([type="password"])').first,
        page.locator('input[name*="user"]:visible:not([type="password"])').first,
        page.locator('input[type="email"]:visible').first,
        page.locator('input[type="text"]:visible').first,
    ):
        try:
            if locator.count():
                locator.first.click(timeout=3000)
                locator.first.fill(username)
                filled_user = True
                break
        except Exception:
            continue
    if not filled_user:
        _die(
            "Could not find a username field. Try PLAYWRIGHT_HEADLESS=false or inspect wb_rfx_login_page.html.",
        )
    pwd_input.fill(password)
    _try_fill_application_number(page, app_no)
    submitted = False
    for locator in (
        page.get_by_role("button", name=re.compile(r"^\s*login\s*$", re.I)),
        page.get_by_role("button", name=re.compile(r"login", re.I)),
        page.locator('button[type="submit"]:visible').first,
        page.locator('input[type="submit"]:visible').first,
    ):
        try:
            if locator.count():
                locator.first.click()
                submitted = True
                break
        except Exception:
            continue
    if not submitted:
        page.keyboard.press("Enter")


def main() -> None:
    _load_env()

    parser = argparse.ArgumentParser(description="WB RFx Now Playwright login + HTML extract")
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "out"),
        help="Directory for HTML/screenshot artefacts",
    )
    parser.add_argument(
        "--post-login-ms",
        type=int,
        default=12_000,
        help="Max wait (ms) for navigation/network after pressing Login",
    )
    parser.add_argument(
        "--initial-wait-ms",
        type=int,
        default=4000,
        help="Idle wait (ms) after load for SPA to render inputs",
    )
    args = parser.parse_args()

    login_url = _req("WB_RFX_AUTH_LOGIN_URL")
    username = _req("WB_RFX_AUTH_USERNAME")
    password = _req("WB_RFX_AUTH_PASSWORD")
    app_no = os.getenv("WB_RFX_AUTH_APP_NUMBER", "").strip()

    headless = _bool_env("PLAYWRIGHT_HEADLESS", True)
    timeout_ms = int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "90000"))
    slow_mo = int(os.getenv("PLAYWRIGHT_SLOW_MO_MS", "0"))

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    masked_user = username[:3] + "***@" + username.split("@", 1)[-1] if "@" in username else username[:2] + "***"
    print(f"WB RFx URL: {login_url}")
    print(f"Username: {masked_user} (masked)")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=slow_mo)
        try:
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 880},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = ctx.new_page()
            page.set_default_timeout(timeout_ms)

            goto_wait = os.getenv("PLAYWRIGHT_GOTO_WAIT", "load")
            page.goto(login_url, wait_until=goto_wait)  # type: ignore[arg-type]
            page.wait_for_timeout(max(500, args.initial_wait_ms))

            pre_login = out / "wb_rfx_login_page.html"
            pre_login.write_text(page.content(), encoding="utf-8")
            print(f"Saved: {pre_login}")

            wb_form_visible = False
            try:
                page.locator("form#loginForm").wait_for(
                    state="visible", timeout=min(45_000, timeout_ms)
                )
                wb_form_visible = True
            except Exception:
                pass

            if wb_form_visible:
                print("Using World Bank RFx form#loginForm selectors.")
                _fill_wbg_rfx_login_form(page, username, password, app_no)
            else:
                print("loginForm not found; using generic visible password/username selectors.")
                _fill_login_generic(page, username, password, app_no, timeout_ms)

            try:
                page.wait_for_load_state("networkidle", timeout=min(args.post_login_ms, timeout_ms))
            except Exception:
                page.wait_for_timeout(min(args.post_login_ms, timeout_ms))

            if wb_form_visible:
                page.wait_for_timeout(max(800, min(3500, args.initial_wait_ms)))
                _maybe_complete_wbg_rfx_email_login_code(
                    page,
                    timeout_ms=timeout_ms,
                    post_submit_ms=args.post_login_ms,
                )
                try:
                    page.wait_for_load_state(
                        "networkidle", timeout=min(args.post_login_ms, timeout_ms)
                    )
                except Exception:
                    page.wait_for_timeout(min(args.post_login_ms, timeout_ms))

            after_html = out / "wb_rfx_after_login.html"
            after_html.write_text(page.content(), encoding="utf-8")
            print(f"Saved: {after_html}")
            png = out / "wb_rfx_final.png"
            page.screenshot(path=str(png), full_page=False)
            print(f"Saved: {png}")
            print(f"Final URL: {page.url}")

        finally:
            browser.close()

    print("Done. If you stopped at MFA, set WB_RFX_LOGIN_CODE or WB_RFX_MFA_STDIN_PROMPT=true and rerun.")


if __name__ == "__main__":
    main()
