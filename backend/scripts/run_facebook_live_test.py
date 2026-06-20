"""Run full Facebook flow step-by-step with console logs (Playwright Chromium)."""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
import traceback

from playwright.async_api import async_playwright

from app.config import get_settings
from app.services.browser_launch import launch_facebook_context
from app.services.facebook_flow import (
    MarketplaceLocation,
    _is_on_vehicles_page,
    _norm_location_city,
    _read_price_filter_state,
    _read_sidebar_location,
    stage_apply_vehicle_price,
    stage_ensure_login,
    stage_open_marketplace,
    stage_scrape_listings,
    stage_set_location,
    wait_then_open_vehicles,
)
from app.services.facebook_session import is_login_fully_complete, save_session
from app.services.matching_engine import parse_price_from_text


def step(msg: str, **details) -> None:
    suffix = f" | {details}" if details else ""
    line = f"[STEP] {msg}{suffix}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", errors="replace").decode("ascii"), flush=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Live Facebook Marketplace flow test")
    p.add_argument("--city", default="Bahawalpur", help="Filter city (default: Bahawalpur)")
    p.add_argument(
        "--country",
        default="",
        help="Filter country — leave empty for city-only (default: empty)",
    )
    p.add_argument("--radius-km", type=int, default=86, help="Radius in km (default: 86)")
    p.add_argument("--min-price", type=float, default=3000.0)
    p.add_argument("--max-price", type=float, default=7000.0)
    p.add_argument("--max-listings", type=int, default=10)
    return p.parse_args()


async def main() -> int:
    args = parse_args()
    cfg = get_settings()
    country = args.country.strip() or None
    location = MarketplaceLocation(city=args.city, country=country, radius_km=args.radius_km)
    nav_timeout = max(cfg.PLAYWRIGHT_TIMEOUT, 120000)
    log = lambda m, d=None, level=None: step(m, **(d or {}))

    step(
        "Test config",
        city=location.city,
        country=location.country,
        radius_km=location.radius_km,
        location_label=location.label,
    )

    playwright = await async_playwright().start()
    browser = None
    context = None
    page = None

    try:
        step("Launch Playwright Chromium (NOT Chrome profile)")
        context, page, browser = await launch_facebook_context(playwright, cfg, headless=False)
        page.set_default_navigation_timeout(nav_timeout)
        page.set_default_timeout(nav_timeout)

        step("Open Marketplace")
        await stage_open_marketplace(page, cfg, log)
        step("After marketplace", url=page.url)

        step("Check login")
        if not await is_login_fully_complete(context, page):
            step("Not logged in — waiting up to 120s for manual login in browser window")
            ok = await stage_ensure_login(page, context, cfg, log)
            if not ok:
                step("FAIL — login not completed in time")
                return 1
        else:
            step("Already logged in (session cookies)")
            await save_session(context, cfg)

        step("Marketplace ready", url=page.url)
        t0 = time.monotonic()
        step("Flow: Marketplace load → /vehicles → location → price")
        await wait_then_open_vehicles(
            page,
            log,
            nav_timeout=nav_timeout,
            location=location,
            refresh=False,
            context=context,
        )
        elapsed = round(time.monotonic() - t0, 2)
        on_vehicles = _is_on_vehicles_page(page)
        step("Vehicles page check", url=page.url, on_vehicles=on_vehicles, seconds=elapsed)
        if not on_vehicles:
            step("FAIL — did not reach /category/vehicles")
            return 1

        step("Set location from filter", city=location.city, country=location.country, radius_km=location.radius_km)
        await stage_set_location(page, location, log)

        sidebar = await _read_sidebar_location(page)
        step("Verify sidebar after Apply", sidebar=sidebar)
        if not sidebar:
            step("FAIL — could not read location on sidebar after Apply")
            return 1

        city_ok = _norm_location_city(location.city) in _norm_location_city(sidebar.get("city", ""))
        radius_diff = abs(sidebar.get("radius_km", 0) - location.radius_km)
        radius_ok = radius_diff <= max(6, int(location.radius_km * 0.08))
        step(
            "Location verify",
            city_match=city_ok,
            radius_match=radius_ok,
            wanted_city=location.city,
            got_city=sidebar.get("city"),
            wanted_radius_km=location.radius_km,
            got_radius_km=sidebar.get("radius_km"),
            raw=sidebar.get("raw"),
        )
        if not city_ok:
            step("FAIL — city not applied on Facebook sidebar")
            return 1
        if not radius_ok:
            step("FAIL — radius not applied on Facebook sidebar", wanted=location.radius_km, got=sidebar.get("radius_km"))
            return 1

        step("Apply Min/Max price", min=args.min_price, max=args.max_price)
        await stage_apply_vehicle_price(page, args.min_price, args.max_price, log)

        price_state = await _read_price_filter_state(page)
        step("Verify price filter state", **price_state)

        def _price_ok(wanted: float | None, got: str | None, got_digits: int | None = None) -> bool:
            if wanted is None or wanted <= 0:
                return True
            if got_digits is not None and got_digits == int(wanted):
                return True
            if not got:
                return False
            digits = re.sub(r"[^\d]", "", got.replace(",", ""))
            return bool(digits) and int(digits) == int(wanted)

        min_ok = _price_ok(
            args.min_price,
            price_state.get("input_min"),
            price_state.get("input_min_value"),
        ) or _price_ok(args.min_price, price_state.get("url_min_price"))
        max_ok = _price_ok(
            args.max_price,
            price_state.get("input_max"),
            price_state.get("input_max_value"),
        ) or _price_ok(args.max_price, price_state.get("url_max_price"))
        step("Price verify", min_ok=min_ok, max_ok=max_ok)
        if args.min_price and args.min_price > 0 and not min_ok:
            step("FAIL — min price not applied in sidebar or URL")
            return 1
        if args.max_price and args.max_price > 0 and not max_ok:
            step("FAIL — max price not applied in sidebar or URL")
            return 1

        step("Scrape listings")
        items = await stage_scrape_listings(page, args.max_listings, log)
        prices = []
        for item in items:
            p = parse_price_from_text(item.get("price_text", ""))
            if p is not None:
                prices.append(p)
            step(
                "Listing",
                title=(item.get("title") or "")[:60],
                price=p,
                price_text=item.get("price_text"),
            )

        below_min = [p for p in prices if args.min_price and p < args.min_price]
        above_max = [p for p in prices if args.max_price and p > args.max_price]
        step(
            "Listing price check",
            count=len(prices),
            below_min=len(below_min),
            above_max=len(above_max),
            sample_below_min=below_min[:3],
            sample_above_max=above_max[:3],
        )
        if below_min or above_max:
            step("WARN — some scraped prices outside filter range (FB may show discounted/stale cards)")

        step("Done", listings=len(items), sample_url=items[0]["url"] if items else None)
        await save_session(context, cfg)
        await asyncio.sleep(2)
        return 0
    except Exception as exc:
        step("ERROR", error=str(exc))
        traceback.print_exc()
        if page:
            step("Last URL", url=page.url)
        return 1
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        try:
            await playwright.stop()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
