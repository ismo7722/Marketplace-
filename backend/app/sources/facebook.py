from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright, TimeoutError as PlaywrightTimeout
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Filter, LogLevel
from app.services.browser_launch import launch_chromium, launch_facebook_context
from app.services.browser_settings import get_playwright_headless, get_playwright_timeout
from app.services.scan_control import is_scan_cancelled
from app.services.facebook_session import (
    has_login_cookies,
    is_login_fully_complete,
    is_on_facebook_auth_flow,
    needs_marketplace_navigation,
    restore_session_file_from_db,
    save_session,
)
from app.services.facebook_flow import (
    MarketplaceLocation,
    _create_context,
    _is_on_vehicles_page,
    _make_db_logger,
    clean_fb_url,
    filters_match_on_page,
    prepare_vehicles_monitoring_page,
    stage_enrich_listing_details,
    stage_ensure_login,
    stage_open_marketplace,
    stage_refresh_listings_page,
    stage_scrape_listings,
)
from app.services.matching_engine import (
    FilterCriteria,
    ListingData,
    infer_fuel_from_text,
    infer_transmission_from_text,
    item_dict_hint_text,
    listing_has_filter_hint,
    parse_mileage_from_text,
    parse_price_from_text,
    parse_year_from_title,
)
from app.sources.base import BaseMarketplaceSource, SourceRegistry

logger = logging.getLogger(__name__)

FB_RADIUS_MILES = [1, 2, 5, 10, 20, 40, 60, 80, 100, 250, 500]


@dataclass(frozen=True)
class FilterScrapeParams:
    city: str
    country: str | None
    radius_km: int
    price_min: float | None
    price_max: float | None

    @classmethod
    def from_filter(cls, db_filter: Filter) -> FilterScrapeParams:
        return cls(
            city=db_filter.city or "Zurich",
            country=db_filter.country or None,
            radius_km=db_filter.radius_km or 65,
            price_min=db_filter.price_min,
            price_max=db_filter.price_max,
        )


def km_to_fb_radius_miles(radius_km: int) -> int:
    miles = radius_km / 1.609344
    return min(FB_RADIUS_MILES, key=lambda m: abs(m - miles))


def _item_to_listing(item: dict) -> ListingData:
    title = item.get("title", "Unknown")
    description = item.get("description") or ""
    combined = f"{title} {description}".strip()
    return ListingData(
        external_id=item["external_id"],
        url=item["url"],
        title=title,
        price=parse_price_from_text(item.get("price_text", "")),
        currency="CHF" if "CHF" in item.get("price_text", "") else "EUR",
        year=parse_year_from_title(combined),
        mileage=parse_mileage_from_text(combined),
        fuel_type=infer_fuel_from_text(combined),
        transmission=infer_transmission_from_text(combined),
        description=description or None,
        location=item.get("location"),
        images=[item["image"]] if item.get("image") else [],
        source="facebook",
    )


class FacebookMarketplaceSource(BaseMarketplaceSource):
    source_name = "facebook"

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._session_location_key: str | None = None
        self._session_price_key: str | None = None
        self._session_vehicles_url: str | None = None

    @staticmethod
    def _price_key(scrape_params: FilterScrapeParams) -> str:
        return f"{scrape_params.price_min}|{scrape_params.price_max}"

    def _clear_session_state(self) -> None:
        self._session_location_key = None
        self._session_price_key = None
        self._session_vehicles_url = None

    def _is_filters_session_valid(
        self,
        page: Page,
        location: MarketplaceLocation,
        scrape_params: FilterScrapeParams,
    ) -> bool:
        if not self.has_live_browser():
            return False
        if is_on_facebook_auth_flow(page):
            return False
        if self._session_location_key != self._location_key(location):
            return False
        if self._session_price_key != self._price_key(scrape_params):
            return False
        url = page.url.lower()
        if "vehicles" not in url and "category_id" not in url:
            return False
        return True

    def _mark_session_filters(
        self,
        page: Page,
        location: MarketplaceLocation,
        scrape_params: FilterScrapeParams,
    ) -> None:
        self._session_location_key = self._location_key(location)
        self._session_price_key = self._price_key(scrape_params)
        self._session_vehicles_url = page.url

    async def _apply_listings_pass(
        self,
        page: Page,
        log,
        criteria: FilterCriteria | None,
        max_results: int,
        *,
        nav_timeout: int,
    ) -> list[ListingData]:
        grid_items = await stage_scrape_listings(page, max_results, log)
        on_page = len(grid_items)
        vehicles_url = page.url
        self._session_vehicles_url = vehicles_url

        if criteria and (criteria.brands or criteria.models):
            hint_items = [
                item
                for item in grid_items
                if listing_has_filter_hint(item_dict_hint_text(item), criteria)
            ]
            log(
                "Stage 5/5 — Detail check for brand/model hints",
                {
                    "on_page": on_page,
                    "hints": len(hint_items),
                    "brands": criteria.brands,
                    "models": criteria.models,
                },
            )
            if hint_items:
                await stage_enrich_listing_details(
                    page, hint_items, log, return_url=vehicles_url, nav_timeout=nav_timeout
                )
            items = hint_items
        else:
            log(
                "Stage 5/5 — Scanning listings (filter-matched only)",
                {"on_page": on_page},
            )
            items = grid_items

        listings = [_item_to_listing(item) for item in items]
        log(
            "Stage 5/5 — Scroll and read complete — passing listings to filter matcher",
            {
                "listings_on_page": on_page,
                "cards_read": len(listings),
            },
        )
        return listings

    @staticmethod
    def _location_key(location: MarketplaceLocation) -> str:
        return f"{location.city}|{location.country or ''}|{location.radius_km}"

    def _playwright_settings(self):
        return get_settings()

    def _browser_options(self) -> tuple[bool, int]:
        return False, get_playwright_timeout()

    def has_live_browser(self) -> bool:
        try:
            return (
                self._context is not None
                and self._page is not None
                and not self._page.is_closed()
            )
        except Exception:
            return False

    async def save_session_and_release(self, db: Session | None = None) -> None:
        """Close browser — only overwrite Neon session when still logged in."""
        if self._context and self.has_live_browser():
            try:
                if await has_login_cookies(self._context):
                    await save_session(self._context, self._playwright_settings())
                else:
                    logger.info("Skip session save on stop — browser not logged in (Neon session kept)")
            except Exception as exc:
                logger.warning("Could not save session before browser close: %s", exc)
        await self.release_browser(db, keep_open=False)

    async def release_browser(self, db: Session | None = None, keep_open: bool = False) -> None:
        log = _make_db_logger(db)

        if not self._context and not self._browser:
            return

        if keep_open and self.has_live_browser():
            return

        context = self._context
        browser = self._browser
        playwright = self._playwright
        self._browser = None
        self._playwright = None
        self._context = None
        self._page = None
        self._clear_session_state()

        if context:
            try:
                await asyncio.wait_for(context.close(), timeout=15)
            except Exception:
                pass
        elif browser:
            try:
                await asyncio.wait_for(browser.close(), timeout=15)
            except Exception:
                pass
        if playwright:
            try:
                await asyncio.wait_for(playwright.stop(), timeout=10)
            except Exception:
                pass
        log("Browser closed")

    async def reset_completely(self, db: Session | None = None) -> dict:
        from app.services.facebook_session import clear_facebook_browser_data

        await self.release_browser(db, keep_open=False)
        await asyncio.sleep(2)
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(clear_facebook_browser_data, self._playwright_settings()),
                timeout=30,
            )
        except asyncio.TimeoutError:
            result = {"session_file": False, "profile_dir": False}
            logger.warning("Profile wipe timed out after 30s")
        log = _make_db_logger(db)
        log("Browser reset — session cleared, next Start is fresh", details=result)
        return result

    def _store_session(
        self,
        playwright: Playwright,
        browser: Browser | None,
        context: BrowserContext,
        page: Page,
    ) -> None:
        self._playwright = playwright
        self._browser = browser
        self._context = context
        self._page = page

    async def _launch_browser(
        self,
        cfg,
        headless: bool,
        log,
    ) -> tuple[Playwright, Browser | None, BrowserContext, Page]:
        playwright = await asyncio.wait_for(async_playwright().start(), timeout=60)
        if headless:
            log("Stage 1/5 — Opening Chromium (headless)", {"headless": True})
        else:
            log("Stage 1/5 — Opening Chromium window", {"headless": False})
        context, page, browser = await launch_facebook_context(playwright, cfg, headless=headless)
        return playwright, browser, context, page

    async def _goto_marketplace_if_needed(
        self,
        page: Page,
        context: BrowserContext,
        cfg,
        log,
        *,
        nav_timeout: int,
    ) -> None:
        if is_on_facebook_auth_flow(page):
            log("Login/verification in progress — bot stays idle (will not navigate away)")
            return
        if needs_marketplace_navigation(page):
            await stage_open_marketplace(
                page, cfg, log, context=context, nav_timeout=nav_timeout
            )

    async def _ensure_marketplace_ready(
        self,
        page: Page,
        context: BrowserContext,
        cfg,
        log,
        *,
        nav_timeout: int,
    ) -> None:
        """Stage 3/5 — Facebook Marketplace home before Vehicles."""
        if is_on_facebook_auth_flow(page):
            return
        if needs_marketplace_navigation(page):
            await stage_open_marketplace(
                page, cfg, log, context=context, nav_timeout=nav_timeout
            )
        else:
            log("Stage 3/5 — Marketplace ready", {"url": clean_fb_url(page.url)})

    async def open_marketplace_browser(self) -> None:
        """Launch Chromium, open Marketplace, wait for manual login + 2FA if needed."""
        cfg = self._playwright_settings()
        log = _make_db_logger(None)
        nav_timeout = max(cfg.PLAYWRIGHT_TIMEOUT, 120000)

        if not self.has_live_browser():
            headless = get_playwright_headless(None)
            log(
                "Opening Playwright Chromium — Facebook Marketplace",
                {"headless": headless},
            )
            playwright = await asyncio.wait_for(async_playwright().start(), timeout=60)
            context, page, browser = await launch_facebook_context(
                playwright, cfg, headless=headless
            )
            self._store_session(playwright, browser, context, page)
        else:
            assert self._context and self._page
            context = self._context
            page = self._page

        page.set_default_navigation_timeout(nav_timeout)
        page.set_default_timeout(nav_timeout)

        if needs_marketplace_navigation(page) and not is_on_facebook_auth_flow(page):
            await stage_open_marketplace(
                page, cfg, log, context=context, nav_timeout=nav_timeout
            )
        elif is_on_facebook_auth_flow(page):
            log("Login/verification in progress — bot stays idle")

        if not await is_login_fully_complete(context, page):
            if not await stage_ensure_login(page, context, cfg, log):
                if is_scan_cancelled():
                    log("Login wait cancelled — Stop or Clear browser was pressed")
                    return
                raise RuntimeError("Facebook login not completed — finish login in the browser window")
        else:
            log("Logged in — ready for monitoring")
            await save_session(context, cfg)

    async def _get_or_create_page(
        self,
        cfg,
        headless: bool,
        log,
    ) -> tuple[Playwright, Browser | None, BrowserContext, Page, bool]:
        if self.has_live_browser():
            assert self._playwright and self._context and self._page
            log("Stage 1/5 — Reusing open browser")
            return self._playwright, self._browser, self._context, self._page, False

        log("Stage 1/5 — Opening browser", {"headless": headless})
        playwright, browser, context, page = await self._launch_browser(cfg, headless, log)
        log("Stage 1/5 — Browser ready")
        self._store_session(playwright, browser, context, page)
        return playwright, browser, context, page, True

    async def run_filter_scrape(
        self,
        db: Session | None,
        scrape_params: FilterScrapeParams,
        max_results: int = 50,
        *,
        criteria: FilterCriteria | None = None,
    ) -> list[ListingData]:
        cfg = self._playwright_settings()
        headless = get_playwright_headless(db)
        log = _make_db_logger(db)
        restore_session_file_from_db(cfg)

        location = MarketplaceLocation(
            city=scrape_params.city,
            country=scrape_params.country,
            radius_km=scrape_params.radius_km,
        )

        playwright: Playwright | None = None
        browser: Browser | None = None
        context: BrowserContext | None = None
        page: Page | None = None

        try:
            playwright, browser, context, page, _is_new_window = await self._get_or_create_page(cfg, headless, log)
            nav_timeout = max(cfg.PLAYWRIGHT_TIMEOUT, 120000)
            page.set_default_navigation_timeout(nav_timeout)
            page.set_default_timeout(nav_timeout)

            if not await stage_ensure_login(page, context, cfg, log, db):
                raise RuntimeError("Facebook login not completed — run login-facebook.bat then Stop → Start")

            if headless:
                from app.config import is_cloud_host
                from app.services.browser_launch import enable_lightweight_browsing

                if is_cloud_host():
                    await enable_lightweight_browsing(context)

            await self._ensure_marketplace_ready(page, context, cfg, log, nav_timeout=nav_timeout)

            session_valid = self._is_filters_session_valid(page, location, scrape_params)

            if not session_valid and _is_on_vehicles_page(page):
                location_ok, price_ok, sidebar_loc, price_state = await filters_match_on_page(
                    page,
                    location,
                    scrape_params.price_min,
                    scrape_params.price_max,
                )
                if location_ok and price_ok:
                    log(
                        "Stage 4/5 — Vehicles ready — Zurich + price already applied",
                        {
                            "location": sidebar_loc["raw"] if sidebar_loc else location.label,
                            "min_price": price_state.get("input_min_value"),
                            "max_price": price_state.get("input_max_value"),
                            "url": page.url,
                        },
                    )
                    self._mark_session_filters(page, location, scrape_params)
                    session_valid = True

            if session_valid:
                log(
                    "Stage 5/5 — Monitoring — refreshing listings",
                    {"url": self._session_vehicles_url or page.url},
                )
                refresh_url = self._session_vehicles_url or page.url
                if refresh_url and refresh_url != page.url:
                    await page.goto(refresh_url, wait_until="domcontentloaded", timeout=nav_timeout)
                    await asyncio.sleep(1.5)
                else:
                    await stage_refresh_listings_page(page, log, nav_timeout=nav_timeout)
                listings = await self._apply_listings_pass(
                    page,
                    log,
                    criteria,
                    max_results,
                    nav_timeout=nav_timeout,
                )
            else:
                try:
                    await prepare_vehicles_monitoring_page(
                        page,
                        log,
                        location,
                        scrape_params.price_min,
                        scrape_params.price_max,
                        nav_timeout=nav_timeout,
                        context=context,
                    )
                except Exception as exc:
                    if not _is_on_vehicles_page(page):
                        raise
                    log(
                        "Stage 4/5 — Vehicles page open — continuing to monitoring despite filter step issue",
                        {"error": str(exc), "url": page.url},
                        level=LogLevel.WARNING,
                    )
                self._mark_session_filters(page, location, scrape_params)
                log(
                    "Stage 5/5 — Monitoring started — scrolling and matching listings",
                    {"url": page.url},
                )
                try:
                    listings = await self._apply_listings_pass(
                        page,
                        log,
                        criteria,
                        max_results,
                        nav_timeout=nav_timeout,
                    )
                except Exception as exc:
                    if _is_on_vehicles_page(page):
                        log(
                            "Stage 5/5 — Listing scan issue on Vehicles page — will retry next cycle",
                            {"error": str(exc), "url": page.url},
                            level=LogLevel.WARNING,
                        )
                        listings = []
                    else:
                        raise

            await save_session(context, cfg)
            self._store_session(playwright, browser, context, page)

        except PlaywrightTimeout as exc:
            log("Scan timed out — will retry later", {"error": str(exc)}, level=LogLevel.WARNING)
            if context and page and not headless:
                self._store_session(playwright, browser, context, page)
            else:
                await self.release_browser(db, keep_open=False)
            raise
        except Exception as exc:
            from app.services.facebook_errors import FacebookLoginRequiredError

            if isinstance(exc, FacebookLoginRequiredError):
                await self.release_browser(db, keep_open=False)
                raise
            logger.exception("Facebook monitoring failed: %s", exc)
            log("Scan failed — see error details", {"error": str(exc)}, level=LogLevel.WARNING)
            if context and page and not headless:
                self._store_session(playwright, browser, context, page)
            else:
                await self.release_browser(db, keep_open=False)
            raise

        return listings

    async def fetch_listings(self, search_url: str, max_results: int = 50) -> list[ListingData]:
        cfg = self._playwright_settings()
        headless, timeout = self._browser_options()
        log = _make_db_logger(None)
        listings: list[ListingData] = []

        try:
            async with async_playwright() as p:
                browser = await launch_chromium(p, headless=headless)
                context, page = await _create_context(browser, cfg, headless=headless)
                await stage_open_marketplace(page, cfg, log)
                if not await stage_ensure_login(page, context, cfg, log):
                    return []
                await page.goto(search_url, wait_until="domcontentloaded", timeout=timeout)
                await asyncio.sleep(3)
                items = await stage_scrape_listings(page, max_results, log)
                for item in items:
                    price = parse_price_from_text(item.get("price_text", ""))
                    listings.append(
                        ListingData(
                            external_id=item["external_id"],
                            url=item["url"],
                            title=item.get("title", "Unknown"),
                            price=price,
                            currency="CHF" if "CHF" in item.get("price_text", "") else "EUR",
                            year=parse_year_from_title(item.get("title", "")),
                            location=item.get("location"),
                            images=[item["image"]] if item.get("image") else [],
                            source="facebook",
                        )
                    )
                await save_session(context, cfg)
                await browser.close()
        except Exception as exc:
            logger.exception("Facebook scrape failed: %s", exc)
        return listings

    async def fetch_listing_details(self, url: str) -> ListingData | None:
        from app.services.matching_engine import parse_number_from_text

        cfg = self._playwright_settings()
        headless, timeout = self._browser_options()
        try:
            async with async_playwright() as p:
                browser = await launch_chromium(p, headless=headless)
                context, page = await _create_context(browser, cfg, headless=headless)
                log = _make_db_logger(None)
                await stage_open_marketplace(page, cfg, log)
                if not await stage_ensure_login(page, context, cfg, log):
                    return None
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                await asyncio.sleep(2)

                data = await page.evaluate("""
                    () => {
                        const title = document.querySelector('h1')?.textContent?.trim() || '';
                        const spans = [...document.querySelectorAll('span')].map(s => s.textContent.trim());
                        const price = spans.find(s => s.includes('CHF') || s.includes('€')) || '';
                        const desc = document.querySelector('[data-ad-preview="message"]')?.textContent
                            || document.querySelector('div[dir="auto"]')?.textContent || '';
                        const images = [...document.querySelectorAll('img')]
                            .map(i => i.src).filter(s => s.includes('scontent') || s.includes('fbcdn'));
                        const location = spans.find(s => s.includes('Zürich') || s.includes('Zurich') || s.includes('km')) || '';
                        return { title, price, description: desc, images: [...new Set(images)].slice(0, 10), location };
                    }
                """)

                id_match = re.search(r"/item/(\d+)", url)
                await save_session(context, cfg)
                await browser.close()

                if not id_match:
                    return None

                combined = f"{data.get('title', '')} {data.get('description', '')}"
                mileage_match = re.search(r"(\d[\d'\s.,]*)\s*km", combined, re.I)
                mileage = parse_number_from_text(mileage_match.group(1)) if mileage_match else None

                return ListingData(
                    external_id=id_match.group(1),
                    url=url,
                    title=data.get("title", "Unknown"),
                    price=parse_price_from_text(data.get("price", "")),
                    currency="CHF",
                    mileage=mileage,
                    year=parse_year_from_title(data.get("title", "")),
                    description=data.get("description"),
                    location=data.get("location"),
                    images=data.get("images", []),
                    source="facebook",
                )
        except Exception as exc:
            logger.exception("Failed to fetch listing details: %s", exc)
            return None


facebook_source = FacebookMarketplaceSource()
SourceRegistry.register(facebook_source)
