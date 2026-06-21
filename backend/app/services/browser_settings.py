"""Playwright always headless for monitoring — login-facebook.bat uses visible browser."""
from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ApplicationSetting


def get_playwright_headless(db: Session | None = None) -> bool:
    """Monitoring is always headless. login-facebook.bat sets FACEBOOK_LOGIN_MODE for visible login."""
    if os.environ.get("FACEBOOK_LOGIN_MODE", "").strip().lower() in ("1", "true", "yes"):
        return False
    return True


def ensure_visible_browser_setting(db: Session) -> None:
    """Keep DB in sync — monitoring always headless."""
    row = db.query(ApplicationSetting).filter(ApplicationSetting.key == "playwright_headless").first()
    if row is None:
        db.add(ApplicationSetting(key="playwright_headless", value="true", category="browser"))
    elif row.value != "true":
        row.value = "true"
    db.commit()


def get_playwright_timeout() -> int:
    return get_settings().PLAYWRIGHT_TIMEOUT
