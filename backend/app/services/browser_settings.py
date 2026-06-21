"""Playwright browser — headless ON/OFF from dashboard; same 7 stages either way."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import ApplicationSetting


def get_playwright_headless(db: Session | None = None) -> bool:
    """False = visible Chromium window. True = headless. Stages 1–7 are identical."""
    settings = get_settings()
    if settings.PLAYWRIGHT_HEADLESS is not None:
        return settings.PLAYWRIGHT_HEADLESS

    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        row = db.query(ApplicationSetting).filter(ApplicationSetting.key == "playwright_headless").first()
        if row is None:
            return False
        return row.value == "true"
    finally:
        if own_session:
            db.close()


def ensure_visible_browser_setting(db: Session) -> None:
    """Default: visible browser (headless off). User changes this in Settings."""
    row = db.query(ApplicationSetting).filter(ApplicationSetting.key == "playwright_headless").first()
    if row is None:
        db.add(ApplicationSetting(key="playwright_headless", value="false", category="browser"))
        db.commit()


def get_playwright_timeout() -> int:
    return get_settings().PLAYWRIGHT_TIMEOUT
