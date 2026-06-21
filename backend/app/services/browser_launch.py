"""Playwright Chromium — session cookies in facebook_session.json."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, Playwright

from app.config import Settings, is_cloud_host
from app.playwright_browsers import configure_playwright_browsers_path, is_chromium_installed
from app.services.facebook_session import USER_AGENT, session_file

configure_playwright_browsers_path()

logger = logging.getLogger(__name__)

LAUNCH_TIMEOUT_SECONDS = 90
DESKTOP_VIEWPORT = {"width": 1920, "height": 1080}
# Smaller viewport on Render — less GPU/RAM while scrolling listings
CLOUD_VIEWPORT = {"width": 1280, "height": 800}
_BLOCKED_RESOURCE_TYPES = frozenset({"image", "media", "font"})

_VISIBLE_ARGS = [
    "--start-maximized",
    "--window-position=0,0",
    "--window-size=1920,1080",
    "--force-device-scale-factor=1",
]

# Required on Linux/Docker (Render) for both headless and visible modes
_LINUX_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-translate",
    "--mute-audio",
    "--no-first-run",
]


def _launch_args(headless: bool) -> list[str]:
    args: list[str] = []
    if is_cloud_host() or headless:
        args.extend(_LINUX_ARGS)
    if not headless:
        args.extend(_VISIBLE_ARGS)
    return args


def _viewport_for_host(*, headless: bool) -> dict:
    if is_cloud_host() or headless:
        return CLOUD_VIEWPORT
    return DESKTOP_VIEWPORT


async def enable_lightweight_browsing(context: BrowserContext) -> None:
    """Block images/media/fonts on Render — keeps Chromium under memory limits."""

    async def _handler(route, request) -> None:
        if request.resource_type in _BLOCKED_RESOURCE_TYPES:
            await route.abort()
        else:
            await route.continue_()

    await context.route("**/*", _handler)


def _context_kwargs(cfg: Settings, *, headless: bool) -> dict:
    viewport = _viewport_for_host(headless=headless)
    kwargs: dict = {
        "locale": "en-US",
        "viewport": viewport,
        "device_scale_factor": 1,
        "screen": {"width": viewport["width"], "height": viewport["height"]},
    }
    if headless:
        kwargs["user_agent"] = USER_AGENT
    path: Path = session_file(cfg)
    if path.exists():
        kwargs["storage_state"] = str(path)
    return kwargs


async def launch_facebook_context(
    playwright: Playwright,
    cfg: Settings,
    *,
    headless: bool,
) -> tuple[BrowserContext, Page, Browser | None]:
    if not is_chromium_installed():
        hint = (
            "Playwright Chromium missing — redeploy backend (Dockerfile)."
            if is_cloud_host()
            else "Run install-chromium.bat once, then press Start."
        )
        raise RuntimeError(hint)
    try:
        browser = await asyncio.wait_for(
            playwright.chromium.launch(
                headless=headless,
                args=_launch_args(headless),
            ),
            timeout=LAUNCH_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        msg = str(exc)
        if "Executable doesn't exist" in msg or "playwright install" in msg.lower():
            hint = (
                "Playwright Chromium not found on server."
                if is_cloud_host()
                else "Run install-chromium.bat once, then press Start again."
            )
            raise RuntimeError(hint) from exc
        raise
    context = await browser.new_context(**_context_kwargs(cfg, headless=headless))
    if is_cloud_host() or headless:
        await enable_lightweight_browsing(context)
    page = await context.new_page()
    if not headless:
        await page.set_viewport_size(_viewport_for_host(headless=headless))
    logger.info(
        "Playwright ready (headless=%s, session=%s)",
        headless,
        session_file(cfg).exists(),
    )
    return context, page, browser


async def launch_chromium(playwright: Playwright, headless: bool) -> Browser:
    return await asyncio.wait_for(
        playwright.chromium.launch(
            headless=headless,
            args=_launch_args(headless),
        ),
        timeout=LAUNCH_TIMEOUT_SECONDS,
    )
