"""Local live verify: Marketplace -> Vehicles -> filters -> Stage 5 monitoring (no SMTP, no hang)."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# No SMTP during verify — Render FREE blocks it anyway; must not block flow.
os.environ.setdefault("DISABLE_SMTP", "1")
os.environ.setdefault("FACEBOOK_LOGIN_MODE", "1")

from playwright.async_api import async_playwright

from app.config import get_settings
from app.database import SessionLocal
from app.models import Filter
from app.playwright_browsers import configure_playwright_browsers_path
from app.services.browser_launch import launch_facebook_context
from app.services.facebook_flow import (
    MarketplaceLocation,
    filters_match_on_page,
    prepare_vehicles_monitoring_page,
    stage_ensure_login,
    stage_open_marketplace,
    stage_scrape_listings,
)
from app.services.facebook_session import (
    get_facebook_session_status,
    is_login_fully_complete,
    persist_session_file_to_db,
    restore_session_file_from_db,
    save_session,
)
from app.services.matching_engine import parse_price_from_text
from app.sources.facebook import FilterScrapeParams
from app.startup_db import run_blocking_startup

STAGE_HELP = {
    "Stage 1/5": "Browser open",
    "Stage 2/5": "Login check — session SQLite/file se load",
    "Stage 3/5": "Marketplace home",
    "Stage 4/5": "/vehicles + Zurich + price URL",
    "Stage 5/5": "Scroll listings + read cards",
}


def say(stage: str, msg: str, details: dict | None = None) -> None:
    help_text = next((v for k, v in STAGE_HELP.items() if k in msg), "")
    line = f"{msg}" + (f" | {details}" if details else "")
    print(line, flush=True)
    if help_text and stage:
        print(f"  -> {help_text}", flush=True)


async def main() -> int:
    configure_playwright_browsers_path()
    cfg = get_settings()

    print("=" * 60, flush=True)
    print("SQLITE (backend/.env)", flush=True)
    print(f"  DATABASE_URL = {cfg.DATABASE_URL}", flush=True)
    print(f"  File         = {( _BACKEND_ROOT / 'data' / 'marketplace_monitor.db').resolve()}", flush=True)
    print(f"  Session file = {cfg.FACEBOOK_SESSION_FILE}", flush=True)
    print("  Backend uses app/database.py -> SessionLocal for ALL reads/writes", flush=True)
    print("=" * 60, flush=True)

    run_blocking_startup(cfg)
    persist_session_file_to_db(cfg)
    restore_session_file_from_db(cfg)
    sess = get_facebook_session_status()
    print(f"Session: {sess}", flush=True)
    if not sess.get("has_session"):
        print("FAIL Stage 2 — run login-facebook.bat first (no session in SQLite/file)", flush=True)
        return 1

    db = SessionLocal()
    try:
        active = db.query(Filter).filter(Filter.is_active == True).first()
        if not active:
            print("FAIL — no active filter in SQLite", flush=True)
            return 1
        params = FilterScrapeParams.from_filter(active)
        location = MarketplaceLocation(
            city=params.city, country=params.country, radius_km=params.radius_km
        )
        min_p, max_p = params.price_min, params.price_max
        print(
            f"Filter from SQLite: {active.name} | {location.label} | CHF {min_p}-{max_p}",
            flush=True,
        )
    finally:
        db.close()

    def log(msg: str, details: dict | None = None, level=None) -> None:
        stage = msg[:10] if msg.startswith("Stage") else ""
        say(stage, msg, details)

    nav_timeout = max(cfg.PLAYWRIGHT_TIMEOUT, 120000)
    playwright = await async_playwright().start()
    try:
        say("1", "Stage 1/5 — Opening browser (visible for local verify)")
        context, page, browser = await launch_facebook_context(playwright, cfg, headless=False)
        page.set_default_navigation_timeout(nav_timeout)
        page.set_default_timeout(nav_timeout)
        say("1", "Stage 1/5 — Browser ready")

        say("3", "Stage 3/5 — Opening Marketplace")
        await stage_open_marketplace(page, cfg, log, context=context, nav_timeout=nav_timeout)

        say("2", "Stage 2/5 — Checking login")
        if not await is_login_fully_complete(context, page):
            ok = await stage_ensure_login(page, context, cfg, log)
            if not ok:
                print("FAIL Stage 2 — logged out / login timeout. Run login-facebook.bat", flush=True)
                return 1
        else:
            log("Stage 2/5 — Logged in (saved session from database)")
        await save_session(context, cfg)

        say("4", "Stage 4/5 — Marketplace -> Vehicles + filters")
        await prepare_vehicles_monitoring_page(
            page, log, location, min_p, max_p, nav_timeout=nav_timeout, context=context
        )
        loc_ok, price_ok, sidebar, price_state = await filters_match_on_page(
            page, location, min_p, max_p
        )
        print(
            f"Filters: location_ok={loc_ok} price_ok={price_ok} | sidebar={sidebar} | price={price_state}",
            flush=True,
        )
        if not loc_ok or not price_ok:
            print("FAIL Stage 4 — filters not applied on Facebook sidebar/URL", flush=True)
            return 2

        say("5", "Stage 5/5 — Monitoring (scroll + read listings)")
        items = await stage_scrape_listings(page, 10, log, scroll_passes=3)
        print(f"Stage 5/5 — Got {len(items)} listings from page", flush=True)
        for item in items[:5]:
            price = parse_price_from_text(item.get("price_text", ""))
            print(f"  listing: {(item.get('title') or '')[:50]} | CHF {price}", flush=True)

        print("=" * 60, flush=True)
        print("PASS — full flow: Marketplace -> Vehicles -> filters -> monitoring", flush=True)
        print("=" * 60, flush=True)
        return 0
    finally:
        await playwright.stop()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
