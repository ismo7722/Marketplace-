"""Scrape live Zurich Vehicles page and update DB filter to match current listings."""
from __future__ import annotations

import asyncio
import json
import re
import sys

from playwright.async_api import async_playwright

from app.config import get_settings
from app.database import SessionLocal
from app.models import Filter, FilterKeyword
from app.services.browser_launch import launch_facebook_context
from app.services.facebook_flow import (
    MarketplaceLocation,
    stage_apply_vehicle_price,
    stage_enrich_listing_details,
    stage_ensure_login,
    stage_open_marketplace,
    stage_scrape_listings,
    stage_set_location,
    wait_then_open_vehicles,
)
from app.services.facebook_session import is_login_fully_complete, save_session
from app.services.matching_engine import (
    FilterCriteria,
    ListingData,
    MatchingEngine,
    infer_fuel_from_text,
    infer_transmission_from_text,
    parse_mileage_from_text,
    parse_price_from_text,
    parse_year_from_title,
)
from app.services.monitoring_service import filter_to_match_criteria

KNOWN_BRANDS = [
    "Volkswagen", "VW", "Audi", "BMW", "Mercedes", "Mercedes-Benz", "Skoda", "Seat",
    "Opel", "Ford", "Renault", "Peugeot", "Citroen", "Toyota", "Honda", "Hyundai",
    "Kia", "Fiat", "Volvo", "Mini", "Porsche", "Nissan", "Mazda", "Suzuki", "Dacia",
    "Chevrolet", "Jeep", "Land Rover", "Range Rover", "Tesla",
]

MODEL_PATTERNS = [
    r"\bVW\s+Golf\b", r"\bGolf\b", r"\bPassat\b", r"\bTouran\b", r"\bPolo\b", r"\bTiguan\b",
    r"\bAudi\s+A3\b", r"\bAudi\s+A4\b", r"\bAudi\s+A6\b", r"\bA3\b", r"\bA4\b",
    r"\bOctavia\b", r"\bSuperb\b", r"\bFabia\b", r"\bLeon\b", r"\bIbiza\b",
    r"\bBMW\s+\d+\b", r"\bSerie\s+\d+\b", r"\b3er\b", r"\b5er\b",
    r"\bC-Class\b", r"\bE-Class\b", r"\bA-Class\b", r"\bClasse\s+C\b",
    r"\bCorolla\b", r"\bYaris\b", r"\bFocus\b", r"\bFiesta\b",
]


def step(msg: str, **kw) -> None:
    print(f"[SYNC] {msg}" + (f" | {kw}" if kw else ""), flush=True)


def title_to_listing(item: dict) -> ListingData:
    title = item.get("title", "Unknown")
    return ListingData(
        external_id=item["external_id"],
        url=item["url"],
        title=title,
        price=parse_price_from_text(item.get("price_text", "")),
        currency="CHF" if "CHF" in item.get("price_text", "") else "EUR",
        year=parse_year_from_title(title),
        mileage=parse_mileage_from_text(title),
        fuel_type=infer_fuel_from_text(title),
        transmission=infer_transmission_from_text(title),
        location=item.get("location"),
        images=[item["image"]] if item.get("image") else [],
        source="facebook",
    )


def detect_brands_models(titles: list[str]) -> tuple[list[str], list[str]]:
    brands: set[str] = set()
    models: set[str] = set()
    blob = " ".join(titles).lower()
    for b in KNOWN_BRANDS:
        if b.lower() in blob or re.search(rf"\b{re.escape(b.lower())}\b", blob):
            brands.add("VW" if b == "Volkswagen" else b)
    if "vw" in blob:
        brands.add("VW")
    if "volkswagen" in blob:
        brands.add("Volkswagen")

    for title in titles:
        for pat in MODEL_PATTERNS:
            m = re.search(pat, title, re.I)
            if m:
                models.add(m.group(0).strip())
        for b in KNOWN_BRANDS:
            m = re.search(rf"\b{re.escape(b)}\b\s+(.{{2,30}})", title, re.I)
            if m:
                chunk = m.group(1).split("\n")[0].strip()
                chunk = re.split(r"\b(KM|km|CHF|€|\$|GODINA|Jahr|Year)\b", chunk)[0].strip()
                if 2 <= len(chunk) <= 25:
                    models.add(chunk)

    if not brands:
        brands = {
            "Volkswagen", "VW", "Audi", "BMW", "Mercedes", "Skoda", "Seat",
            "Ford", "Opel", "Renault", "Toyota", "Yamaha", "Suzuki", "Peugeot",
        }
    if not models:
        models = {"Golf", "Passat", "A3", "A4", "Octavia", "Leon", "Touran", "Polo", "Tiguan"}

    return sorted(brands), sorted(models, key=len, reverse=True)[:25]


async def scrape_live() -> list[ListingData]:
    cfg = get_settings()
    location = MarketplaceLocation(city="Zurich", country="Switzerland", radius_km=65)
    nav_timeout = max(cfg.PLAYWRIGHT_TIMEOUT, 120000)
    log = lambda m, d=None, level=None: None

    playwright = await async_playwright().start()
    context = page = browser = None
    try:
        context, page, browser = await launch_facebook_context(playwright, cfg, headless=False)
        page.set_default_navigation_timeout(nav_timeout)
        page.set_default_timeout(nav_timeout)

        await stage_open_marketplace(page, cfg, log)
        if not await is_login_fully_complete(context, page):
            ok = await stage_ensure_login(page, context, cfg, log)
            if not ok:
                raise RuntimeError("Login required")
        await save_session(context, cfg)

        await wait_then_open_vehicles(page, log, nav_timeout=nav_timeout, location=location, refresh=False, context=context)
        await stage_set_location(page, location, log)
        await stage_apply_vehicle_price(page, 3000.0, 7000.0, log)
        items = await stage_scrape_listings(page, 25, log)
        await stage_enrich_listing_details(page, items, log, return_url=page.url)
        await save_session(context, cfg)
        return [title_to_listing(i) for i in items]
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


def update_filter(db, brands: list[str], models: list[str], matched_count: int) -> None:
    f = db.query(Filter).filter(Filter.is_active == True).first()
    if not f:
        raise RuntimeError("No active filter in database")

    f.city = "Zurich"
    f.country = "Switzerland"
    f.radius_km = 65
    f.price_min = 3000
    f.price_max = 7000
    f.brands = json.dumps(brands)
    f.models = json.dumps(models)
    f.fuel_types = json.dumps([])
    f.transmission_types = json.dumps([])
    f.mileage_max = None
    f.min_match_score = 70.0

    db.query(FilterKeyword).filter(
        FilterKeyword.filter_id == f.id, FilterKeyword.keyword_type == "include"
    ).delete()

    db.commit()
    step(
        "Filter updated in database",
        name=f.name,
        id=f.id,
        brands=len(brands),
        models=len(models),
        matched_live=matched_count,
    )


async def main() -> int:
    step("Scraping live Zurich Vehicles (3000-7000 CHF)...")
    listings = await scrape_live()
    step("Scraped from page", count=len(listings))
    for i, L in enumerate(listings[:8], 1):
        step(f"  {i}", title=L.title[:70], price=L.price, chf=L.currency)

    brands, models = detect_brands_models([L.title for L in listings])
    step("Detected from live titles", brands=brands[:12], models=models[:12])

    db = SessionLocal()
    try:
        f = db.query(Filter).filter(Filter.is_active == True).first()
        if not f:
            step("FAIL — no filter in DB")
            return 1

        criteria = filter_to_match_criteria(f, db)
        criteria.brands = brands
        criteria.models = models
        criteria.fuel_types = []
        criteria.transmission_types = []
        criteria.include_keywords = []
        criteria.mileage_max = None

        engine = MatchingEngine()
        matched = []
        for L in listings:
            ok, res = engine.is_full_match(L, criteria)
            if ok:
                matched.append(L)

        step("Match preview with new brands/models (no include keywords)", matched=len(matched), total=len(listings))

        update_filter(db, brands, models, len(matched))

        criteria2 = filter_to_match_criteria(f, db)
        criteria2.include_keywords = []
        matched2 = sum(1 for L in listings if engine.is_full_match(L, criteria2)[0])
        step("After DB update", matched=matched2, total=len(listings))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
