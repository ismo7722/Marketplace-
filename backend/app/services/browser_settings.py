"""Playwright headless on cloud (Render); visible browser on local PC."""
from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.config import get_settings, is_cloud_host
from app.models import ApplicationSetting


def get_playwright_headless(db: Session | None = None) -> bool:
    """Cloud = headless. Local PC = visible browser unless PLAYWRIGHT_HEADLESS=true in .env."""
    if os.environ.get("FACEBOOK_LOGIN_MODE", "").strip().lower() in ("1", "true", "yes"):
        return False
    if is_cloud_host():
        return True
    settings = get_settings()
    if settings.PLAYWRIGHT_HEADLESS is not None:
        return settings.PLAYWRIGHT_HEADLESS
    return False


def ensure_visible_browser_setting(db: Session) -> None:
    """Sync browser mode: headless on Render, visible locally."""
    expected = "true" if is_cloud_host() else "false"
    row = db.query(ApplicationSetting).filter(ApplicationSetting.key == "playwright_headless").first()
    if row is None:
        db.add(ApplicationSetting(key="playwright_headless", value=expected, category="browser"))
    elif is_cloud_host() and row.value != "true":
        row.value = "true"
    elif not is_cloud_host() and row.value != "false":
        row.value = "false"
    db.commit()


def get_playwright_timeout() -> int:
    return get_settings().PLAYWRIGHT_TIMEOUT
