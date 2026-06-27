"""Pre-deploy check: Neon session in DB + headless Stage 2 login (same as Render)."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("PLAYWRIGHT_HEADLESS", "true")
os.environ.setdefault("RENDER", "true")

from playwright.async_api import async_playwright

from app.config import get_settings
from app.database import SessionLocal
from app.models import ApplicationSetting
from app.playwright_browsers import configure_playwright_browsers_path
from app.services.browser_launch import launch_facebook_context
from app.services.facebook_flow import stage_ensure_login
from app.services.facebook_session import (
    SESSION_DB_KEY,
    get_facebook_session_status,
    has_facebook_session_saved,
    restore_session_file_from_db,
)
from app.startup_db import run_blocking_startup


async def main() -> int:
    configure_playwright_browsers_path()
    cfg = get_settings()
    print("=" * 60)
    print("PRE-DEPLOY SESSION CHECK")
    print("=" * 60)
    print(f"DATABASE_URL starts with: {cfg.DATABASE_URL[:30]}...")

    run_blocking_startup(cfg)
    restore_session_file_from_db(cfg)
    status = get_facebook_session_status()
    print(f"Session status: {status}")

    db = SessionLocal()
    try:
        row = db.query(ApplicationSetting).filter(ApplicationSetting.key == SESSION_DB_KEY).first()
        if row and row.value:
            print(f"Neon session row: OK ({len(row.value)} chars)")
        else:
            print("FAIL — No session in Neon. Run login-facebook.bat first.")
            return 1
    finally:
        db.close()

    if not has_facebook_session_saved(cfg):
        print("FAIL — has_facebook_session_saved=False")
        return 1

    def log(msg: str, details: dict | None = None, level=None) -> None:
        print(msg if not details else f"{msg} | {details}", flush=True)

    print("\nHeadless Stage 2 test (same path as Render)...")
    playwright = await async_playwright().start()
    try:
        context, page, browser = await launch_facebook_context(playwright, cfg, headless=True)
        nav_timeout = max(cfg.PLAYWRIGHT_TIMEOUT, 120000)
        page.set_default_navigation_timeout(nav_timeout)
        page.set_default_timeout(nav_timeout)

        ok = await stage_ensure_login(page, context, cfg, log)
        if ok:
            print("\nPASS — Stage 2 headless login OK (Render should work after deploy)")
            return 0
        print("\nFAIL — Stage 2 headless login failed")
        return 2
    finally:
        await playwright.stop()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
