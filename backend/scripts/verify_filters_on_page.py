"""Verify sidebar location + price read/skip on live Facebook Vehicles page."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from playwright.async_api import async_playwright

from app.config import get_settings
from app.playwright_browsers import configure_playwright_browsers_path
from app.services.browser_launch import launch_facebook_context
from app.services.facebook_flow import (
    MarketplaceLocation,
    filters_match_on_page,
    prepare_vehicles_monitoring_page,
    stage_ensure_login,
    stage_open_marketplace,
)
from app.services.facebook_session import is_login_fully_complete, restore_session_file_from_db
from app.startup_db import run_blocking_startup


async def main() -> int:
    configure_playwright_browsers_path()
    cfg = get_settings()
    run_blocking_startup(cfg)
    restore_session_file_from_db(cfg)

    location = MarketplaceLocation(city="Zurich", country="Switzerland", radius_km=65)
    min_price = 3000.0
    max_price = 7000.0

    def log(msg: str, details: dict | None = None) -> None:
        print(msg if not details else f"{msg} | {details}", flush=True)

    playwright = await async_playwright().start()
    try:
        context, page, browser = await launch_facebook_context(playwright, cfg, headless=False)
        nav_timeout = max(cfg.PLAYWRIGHT_TIMEOUT, 120000)
        page.set_default_navigation_timeout(nav_timeout)
        page.set_default_timeout(nav_timeout)

        await stage_open_marketplace(page, cfg, log, context=context, nav_timeout=nav_timeout)
        if not await is_login_fully_complete(context, page):
            ok = await stage_ensure_login(page, context, cfg, log)
            if not ok:
                print("ERROR: Facebook login required — run login-facebook.bat first", flush=True)
                return 1

        await prepare_vehicles_monitoring_page(
            page,
            log,
            location,
            min_price,
            max_price,
            nav_timeout=nav_timeout,
        )

        location_ok, price_ok, sidebar_loc, price_state = await filters_match_on_page(
            page, location, min_price, max_price
        )
        print("=" * 60, flush=True)
        print(f"URL: {page.url}", flush=True)
        print(f"Sidebar location: {sidebar_loc}", flush=True)
        print(f"Price state: {price_state}", flush=True)
        print(f"location_ok={location_ok} price_ok={price_ok}", flush=True)
        print("=" * 60, flush=True)
        await asyncio.sleep(3)
        return 0 if location_ok and price_ok else 2
    finally:
        await playwright.stop()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
