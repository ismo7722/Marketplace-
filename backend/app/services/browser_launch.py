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
]


def _launch_args(headless: bool) -> list[str]:
    args: list[str] = []
    if is_cloud_host() or headless:
        args.extend(_LINUX_ARGS)
    if not headless:
        args.extend(_VISIBLE_ARGS)
    return args


def _context_kwargs(cfg: Settings, *, headless: bool) -> dict:
    kwargs: dict = {
        "locale": "en-US",
        "viewport": DESKTOP_VIEWPORT,
        "device_scale_factor": 1,
        "screen": {"width": 1920, "height": 1080},
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
    page = await context.new_page()
    if not headless:
        await page.set_viewport_size(DESKTOP_VIEWPORT)
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
