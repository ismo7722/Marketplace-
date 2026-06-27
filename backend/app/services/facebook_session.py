"""Facebook session — Playwright cookies in file + database (shared with Render)."""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import time
from pathlib import Path

from playwright.async_api import BrowserContext, Page

from app.config import Settings, get_settings
from app.services.scan_control import is_scan_cancelled

logger = logging.getLogger(__name__)

SESSION_DB_KEY = "facebook_session_storage"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

MARKETPLACE_URL = "https://www.facebook.com/marketplace/"
PASSIVE_LOGIN_POLL_SECONDS = 2
POST_LOGIN_SETTLE_SECONDS = 5


def session_file(cfg: Settings) -> Path:
    path = Path(cfg.FACEBOOK_SESSION_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def profile_dir(cfg: Settings | None = None) -> Path:
    cfg = cfg or get_settings()
    path = Path(cfg.FACEBOOK_PROFILE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def clear_facebook_browser_data(cfg: Settings | None = None) -> dict:
    cfg = cfg or get_settings()
    removed_session = clear_session_file(cfg)
    profile = profile_dir(cfg)
    removed_profile = False
    profile_still_exists = False

    if profile.exists():
        for attempt in range(5):
            try:
                shutil.rmtree(profile)
                removed_profile = True
                break
            except Exception as exc:
                logger.warning("Profile delete attempt %s/5 failed: %s", attempt + 1, exc)
                time.sleep(0.8 * (attempt + 1))
        profile_still_exists = profile.exists()

    profile.mkdir(parents=True, exist_ok=True)
    return {
        "session_file": removed_session,
        "profile_dir": removed_profile and not profile_still_exists,
        "profile_cleared": not profile_still_exists,
    }


def clear_session_file(cfg: Settings | None = None) -> bool:
    cfg = cfg or get_settings()
    path = session_file(cfg)
    removed = False
    if path.exists():
        path.unlink()
        removed = True
    clear_session_in_db()
    return removed


def clear_session_in_db() -> None:
    from app.database import SessionLocal
    from app.models import ApplicationSetting

    db = SessionLocal()
    try:
        row = db.query(ApplicationSetting).filter(ApplicationSetting.key == SESSION_DB_KEY).first()
        if row:
            db.delete(row)
            db.commit()
    finally:
        db.close()


def has_facebook_session_saved(cfg: Settings | None = None) -> bool:
    cfg = cfg or get_settings()
    path = session_file(cfg)
    if path.exists() and path.stat().st_size > 20:
        return True
    from app.database import SessionLocal
    from app.models import ApplicationSetting

    db = SessionLocal()
    try:
        row = db.query(ApplicationSetting).filter(ApplicationSetting.key == SESSION_DB_KEY).first()
        return bool(row and row.value and len(row.value.strip()) > 20)
    finally:
        db.close()


def persist_session_file_to_db(cfg: Settings | None = None) -> bool:
    cfg = cfg or get_settings()
    path = session_file(cfg)
    if not path.exists() or path.stat().st_size < 20:
        return False
    from app.database import SessionLocal
    from app.models import ApplicationSetting

    content = path.read_text(encoding="utf-8")
    db = SessionLocal()
    try:
        row = db.query(ApplicationSetting).filter(ApplicationSetting.key == SESSION_DB_KEY).first()
        if row:
            row.value = content
            row.category = "facebook"
        else:
            db.add(ApplicationSetting(key=SESSION_DB_KEY, value=content, category="facebook"))
        db.commit()
        logger.info("Facebook session saved to database")
        return True
    finally:
        db.close()


def restore_session_file_from_db(cfg: Settings | None = None) -> bool:
    """Copy DB session to local file so Playwright can load cookies on Render."""
    cfg = cfg or get_settings()
    path = session_file(cfg)
    from app.database import SessionLocal
    from app.models import ApplicationSetting

    db = SessionLocal()
    try:
        row = db.query(ApplicationSetting).filter(ApplicationSetting.key == SESSION_DB_KEY).first()
        if not row or not row.value or len(row.value.strip()) < 20:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(row.value, encoding="utf-8")
        return True
    finally:
        db.close()


def get_facebook_session_status() -> dict:
    cfg = get_settings()
    path = session_file(cfg)
    file_ok = path.exists() and path.stat().st_size > 20
    db_ok = False
    from app.database import SessionLocal
    from app.models import ApplicationSetting

    db = SessionLocal()
    try:
        row = db.query(ApplicationSetting).filter(ApplicationSetting.key == SESSION_DB_KEY).first()
        db_ok = bool(row and row.value and len(row.value.strip()) > 20)
    finally:
        db.close()
    return {
        "has_session": file_ok or db_ok,
        "has_file": file_ok,
        "has_database": db_ok,
    }


def is_on_facebook_auth_flow(page: Page) -> bool:
    """Passive URL check — user is still logging in or on Facebook verification."""
    url = page.url.lower()
    if any(
        token in url
        for token in (
            "checkpoint",
            "two_step",
            "two_step_verification",
            "authentication",
            "confirmemail",
            "recover",
        )
    ):
        return True
    if "/login" in url and "marketplace" not in url:
        return True
    return False


def needs_marketplace_navigation(page: Page) -> bool:
    """True when browser should go to Marketplace — never during login/2FA."""
    if is_on_facebook_auth_flow(page):
        return False
    url = page.url.lower().strip()
    if not url or url == "about:blank" or url.startswith("chrome://"):
        return True
    return "marketplace" not in url


async def has_login_cookies(context: BrowserContext) -> bool:
    """Passive — full Facebook session (login + verification done)."""
    try:
        names = {c.get("name") for c in await context.cookies() if c.get("value")}
        return "c_user" in names and "xs" in names
    except Exception:
        pass
    return False


async def is_login_fully_complete(context: BrowserContext, page: Page) -> bool:
    """
    Login is done only when full session cookies exist, auth pages are left,
    and Marketplace is usable (guest preview does not count as logged in).
    """
    if not await has_login_cookies(context):
        return False
    if is_on_facebook_auth_flow(page):
        return False
    return await _is_marketplace_ready(page, context)


async def _has_login_wall(page: Page) -> bool:
    if is_on_facebook_auth_flow(page):
        return True
    for phrase in ("See more on Facebook", "Log in to Facebook", "Log Into Facebook"):
        try:
            if await page.get_by_text(phrase, exact=False).first.is_visible(timeout=400):
                return True
        except Exception:
            pass
    return False


async def _login_overlay_visible(page: Page) -> bool:
    if is_on_facebook_auth_flow(page):
        return False
    patterns = (
        r"See more on Facebook",
        r"Log in to Facebook",
        r"Log Into Facebook",
        r"Create new account",
    )
    try:
        dialogs = page.locator('[role="dialog"], [aria-modal="true"]')
        count = await dialogs.count()
        for i in range(count):
            dialog = dialogs.nth(i)
            if not await dialog.is_visible(timeout=300):
                continue
            text = await dialog.inner_text()
            if any(re.search(p, text, re.I) for p in patterns):
                return True
    except Exception:
        pass
    return False


async def _is_marketplace_ready(page: Page, context: BrowserContext | None = None) -> bool:
    if is_on_facebook_auth_flow(page):
        return False
    if context is not None and not await has_login_cookies(context):
        return False
    if await _has_login_wall(page):
        return False
    if await _login_overlay_visible(page):
        return False

    for sel in (
        'input[placeholder*="Search Marketplace" i]',
        'a[href*="/marketplace/category/"]',
        'a[href*="/marketplace/item/"]',
    ):
        try:
            if await page.locator(sel).first.is_visible(timeout=1500):
                return True
        except Exception:
            continue
    return False


async def _is_login_required(page: Page) -> bool:
    if is_on_facebook_auth_flow(page):
        return True
    if await _has_login_wall(page):
        return True
    if await _login_overlay_visible(page):
        return True
    return not await _is_marketplace_ready(page)


async def dismiss_login_popup_once(page: Page) -> bool:
    """
    Close the Marketplace login modal (X) so the user can log in via the top header
    Email/Password fields — not through the popup (popup uses a separate Facebook flow).
    Never runs on login/checkpoint/authentication pages.
    """
    if is_on_facebook_auth_flow(page):
        return False
    if "marketplace" not in page.url.lower():
        return False

    try:
        dialog = page.locator('[role="dialog"]').filter(
            has_text=re.compile(r"See more on Facebook|Log in to Facebook", re.I)
        ).first
        if not await dialog.is_visible(timeout=2000):
            return False
        close_btn = dialog.locator('[aria-label="Close"], [aria-label="close"]').first
        if await close_btn.is_visible(timeout=800):
            await close_btn.click()
            await asyncio.sleep(1.0)
            return True
    except Exception:
        pass
    return False


async def dismiss_all_login_overlays(page: Page) -> bool:
    return await dismiss_login_popup_once(page)


async def reload_marketplace_after_login(page: Page, cfg: Settings) -> None:
    """Only after login + authentication fully finished — never during checkpoint."""
    if is_on_facebook_auth_flow(page):
        return
    await page.goto(
        MARKETPLACE_URL,
        wait_until="domcontentloaded",
        timeout=max(cfg.PLAYWRIGHT_TIMEOUT, 90000),
    )
    await asyncio.sleep(2)
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=12000)
    except Exception:
        pass


async def wait_passive_for_login(
    context: BrowserContext,
    page: Page,
    *,
    timeout_seconds: int = 900,
) -> bool:
    """Bot is completely static while user logs in manually (login-facebook.bat window)."""
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        if is_scan_cancelled():
            return False
        if await is_login_fully_complete(context, page):
            return True
        await asyncio.sleep(PASSIVE_LOGIN_POLL_SECONDS)
    return False


async def wait_until_marketplace_logged_in(
    page: Page,
    context: BrowserContext,
    cfg: Settings,
    *,
    log_fn=None,
    timeout_seconds: int = 900,
) -> bool:
    if log_fn:
        log_fn(
            "Bot paused — finish login and any Facebook verification in the browser",
            {"timeout_seconds": timeout_seconds},
        )
    return await wait_passive_for_login(context, page, timeout_seconds=timeout_seconds)


async def save_session(context: BrowserContext, cfg: Settings) -> None:
    try:
        path = session_file(cfg)
        await context.storage_state(path=str(path))
        persist_session_file_to_db(cfg)
    except Exception as exc:
        logger.warning("Could not save session backup: %s", exc)
