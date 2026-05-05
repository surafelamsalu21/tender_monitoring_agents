#!/usr/bin/env python3
"""
CIDA Procurement (Canada) — Playwright probe: open login redirect URL, sign in when possible,
optionally answer a security‑question challenge, save HTML/screenshot.

The entry URL commonly redirects onto the broader Canada **Sign-In / GCKey** experience.
Flows change; selectors are heuristic. Use headed mode plus saved HTML when tweaking.

Prerequisites:
  pip install playwright python-dotenv
  playwright install chromium

Required .env
  CIDA_AUTH_LOGIN_URL   — e.g. https://pi.international.gc.ca/pages/sec/loginRedirect.xhtml?lang=en
  CIDA_AUTH_USERNAME    — GCKey username (or PI login id supplied by GCKey)
  CIDA_AUTH_PASSWORD

Optional security questions (no OTP by default — but GC may later add MFA/SMS separately)
------------------------------------------------------------------
If the portal shows a **recovery / security question** page, answers can be wired without
hard-coding selectors for every question wording:

  CIDA_AUTH_SECURITY_MAP
      Semicolon‑separated pairs:  SubstringSnippet=Answer
      The snippet is matched **case‑insensitive** against visible page text; first match wins.
      Only the **first substring** delimiter `=` separates key from answer (answers may contain "=").

      Example (single line in .env, no quotes usually needed):
        CIDA_AUTH_SECURITY_MAP=Mother's maiden=Doe;maternal grandmother=Ada;high school=Wellington

  CIDA_AUTH_SECURITY_PROMPT_STDIN=true
      If a likely security‑question screen appears and no substring from SECURITY_MAP matched,
      the script prompts in this terminal: paste the answer and press Enter.

  CIDA_AUTH_SECURITY_WAIT_MS (default 20000)
      How long to wait for a challenge screen after password submit.

Other optional
  PLAYWRIGHT_HEADLESS — default true; use false while debugging redirects
  PLAYWRIGHT_TIMEOUT_MS
  PLAYWRIGHT_GOTO_WAIT — default domcontentloaded (GC redirects can hang on \"networkidle\")
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


def _parse_security_map(raw: str) -> dict[str, str]:
    """
    "Mother=Jane;favorite city=Vancouver" -> {"mother":"Jane","favorite city":"Vancouver"}
    """
    mapping: dict[str, str] = {}
    if not raw or not raw.strip():
        return mapping
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        key, val = chunk.split("=", 1)
        key, val = key.strip(), val.strip()
        if key:
            mapping[key.lower()] = val
    return mapping


def _body_text_lower(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=8000).lower()
    except Exception:
        return ""


def _likely_security_challenge_page(page) -> bool:
    t = _body_text_lower(page)
    needles = (
        "security question",
        "secret question",
        "question de sécurité",
        "réponse secrète",
        "verification question",
        "help us verify",
    )
    if not any(n in t for n in needles):
        return False
    # Exclude obvious password-only chrome
    tb = page.locator(
        'input[type="text"]:visible, '
        'input:not([type="hidden"]):not([type="password"]):not([type="checkbox"]):not([type="radio"]):not([type="submit"]):visible'
    ).count()
    ta = page.locator("textarea:visible").count()
    return tb + ta >= 1


def _visible_answer_field(page):
    if page.locator('input[type="text"]:visible').count():
        return page.locator('input[type="text"]:visible').first
    loc = page.locator(
        'input:not([type="password"]):not([type="hidden"]):not([type="checkbox"])'
        ':not([type="radio"]):not([type="submit"]):not([type="button"]):visible'
    ).first
    if loc.count():
        return loc
    ta = page.locator("textarea:visible")
    if ta.count():
        return ta.first
    return None


def _answer_security_challenge(page, mapping: dict[str, str]) -> bool:
    """Return True when an answer field was submitted."""
    body = _body_text_lower(page)
    for needle, ans in mapping.items():
        if needle.lower() not in body:
            continue
        field = _visible_answer_field(page)
        if field is None:
            print(f"Matched '{needle}' in page text but found no visible answer field.", file=sys.stderr)
            return False
        field.click()
        field.fill(ans)
        for btn in (
            page.get_by_role("button", name=re.compile(r"continue|submit|connexion|next|sign\s*in", re.I)),
            page.locator('button[type="submit"]:visible').first,
            page.locator('input[type="submit"]:visible').first,
        ):
            try:
                if btn.count():
                    btn.first.click()
                    return True
            except Exception:
                continue
        page.keyboard.press("Enter")
        return True
    return False


def _click_first_login_submit(page) -> None:
    for btn in (
        page.get_by_role("button", name=re.compile(r"sign\s*in|log\s*in|connexion|continuer", re.I)),
        page.locator('button[type="submit"]:visible').first,
        page.locator('input[type="submit"]:visible').first,
    ):
        try:
            if btn.count():
                btn.first.click()
                return
        except Exception:
            continue
    page.keyboard.press("Enter")


def _fill_username_password_best_effort(page, username: str, password: str, timeout_ms: int) -> bool:
    """Return True when password was filled."""
    pwd = page.locator('input[type="password"]:visible').first
    try:
        pwd.wait_for(state="visible", timeout=timeout_ms)
    except Exception:
        return False

    filled_user = False
    for locator in (
        page.get_by_role("textbox", name=re.compile(r"username|user\s*name|gckey|courriel|email", re.I)),
        page.get_by_placeholder(re.compile(r"username|courriel|email|user", re.I)),
        page.locator('input[id*="username"]:visible'),
        page.locator('input[name*="username"]:visible'),
        page.locator('input[type="email"]:visible').first,
        page.locator('input[type="text"]:visible').first,
    ):
        try:
            if locator.count():
                locator.first.click(timeout=2000)
                locator.first.fill(username)
                filled_user = True
                break
        except Exception:
            continue

    if not filled_user:
        print("Could not confidently locate username field.", file=sys.stderr)
        return False

    pwd.click()
    pwd.fill(password)
    return True


def main() -> None:
    _load_env()

    parser = argparse.ArgumentParser(description="CIDA/GC Sign-In Playwright probe")
    parser.add_argument("--output-dir", default=str(ROOT / "out"), help="Artefacts directory")
    parser.add_argument(
        "--wait-after-password-ms",
        type=int,
        default=4500,
        help="Pause after submitting password before checking for security questions",
    )
    args = parser.parse_args()

    login_url = _req("CIDA_AUTH_LOGIN_URL")
    username = _req("CIDA_AUTH_USERNAME")
    password = _req("CIDA_AUTH_PASSWORD")

    headless = _bool_env("PLAYWRIGHT_HEADLESS", True)
    timeout_ms = int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "120000"))
    slow_mo = int(os.getenv("PLAYWRIGHT_SLOW_MO_MS", "0"))
    goto_wait = os.getenv("PLAYWRIGHT_GOTO_WAIT", "domcontentloaded")
    sec_wait_ms = min(int(os.getenv("CIDA_AUTH_SECURITY_WAIT_MS", "20000")), timeout_ms)

    security_map_raw = os.getenv("CIDA_AUTH_SECURITY_MAP", "")
    sec_mapping = _parse_security_map(security_map_raw)

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"CIDA/GC redirect URL: {login_url}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=slow_mo)
        try:
            ctx = browser.new_context(viewport={"width": 1360, "height": 900})
            page = ctx.new_page()
            page.set_default_timeout(timeout_ms)

            page.goto(login_url, wait_until=goto_wait)  # type: ignore[arg-type]
            (out / "cida_after_redirect.html").write_text(page.content(), encoding="utf-8")
            print(f"Saved: {out / 'cida_after_redirect.html'} (final URL after goto: {page.url})")

            if not _fill_username_password_best_effort(page, username, password, timeout_ms):
                _die("Password field never became visible — inspect cida_after_redirect.html")

            _click_first_login_submit(page)

            page.wait_for_timeout(max(800, args.wait_after_password_ms))

            # Optional security question page
            try:
                page.wait_for_function(
                    "document.readyState === 'complete'",
                    timeout=min(25000, timeout_ms),
                )
            except Exception:
                pass

            sec_deadline = sec_wait_ms
            while sec_deadline > 0:
                slice_ms = min(4000, sec_deadline)
                page.wait_for_timeout(slice_ms)
                sec_deadline -= slice_ms
                if _likely_security_challenge_page(page):
                    break
                if page.locator('input[type="password"]:visible').count() > 1:
                    break

            if _likely_security_challenge_page(page):
                print("Security / verification challenge page detected.")
                if not sec_mapping:
                    print(
                        "Define CIDA_AUTH_SECURITY_MAP (snippet=answer;...) "
                        "or CIDA_AUTH_SECURITY_PROMPT_STDIN=true",
                        file=sys.stderr,
                    )
                if sec_mapping:
                    answered = _answer_security_challenge(page, sec_mapping)
                    if answered:
                        print("Filled answer from CIDA_AUTH_SECURITY_MAP and clicked submit.")
                    elif _bool_env("CIDA_AUTH_SECURITY_PROMPT_STDIN", False):
                        ans = ""
                        try:
                            ans = input("Security answer (visible on screen): ").strip()
                        except EOFError:
                            pass
                        if ans:
                            field = _visible_answer_field(page)
                            if field:
                                field.click()
                                field.fill(ans)
                                _click_first_login_submit(page)

                elif _bool_env("CIDA_AUTH_SECURITY_PROMPT_STDIN", False):
                    ans = ""
                    try:
                        ans = input("Security answer (visible on screen): ").strip()
                    except EOFError:
                        pass
                    if ans:
                        field = _visible_answer_field(page)
                        if field:
                            field.click()
                            field.fill(ans)
                            _click_first_login_submit(page)

            page.wait_for_timeout(3000)
            page.screenshot(path=str(out / "cida_final.png"), full_page=False)
            post = out / "cida_after_login_attempt.html"
            post.write_text(page.content(), encoding="utf-8")
            print(f"Saved: {post}")
            print(f"Saved: {out / 'cida_final.png'}")
            print(f"Final URL: {page.url}")

        finally:
            browser.close()

    print(
        "Done. GCKey sometimes adds MFA later in the journey — capture HTML if a new blocker appears "
        "(SMS, email link, CRA-style 2SV)."
    )


if __name__ == "__main__":
    main()
