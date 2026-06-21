"""One-time Facebook login on your PC — saves session to database for Render headless bot."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ["FACEBOOK_LOGIN_MODE"] = "1"

from app.config import get_settings
from app.playwright_browsers import configure_playwright_browsers_path
from app.services.facebook_session import get_facebook_session_status, persist_session_file_to_db
from app.sources.facebook import FacebookMarketplaceSource
from app.startup_db import run_blocking_startup

configure_playwright_browsers_path()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> int:
    settings = get_settings()
    print("=" * 60)
    print("Facebook Login — visible Chromium window will open")
    print("Log in to Facebook (including 2FA). Session saves to your database.")
    print("After this, Render can run ALL stages headless.")
    print("=" * 60)

    run_blocking_startup(settings)

    fb = FacebookMarketplaceSource()
    try:
        await fb.open_marketplace_browser()
        persist_session_file_to_db(settings)
        status = get_facebook_session_status()
        if status.get("has_session"):
            print("\nSUCCESS — Facebook session saved.")
            print("Dashboard: Stop → Start — 5-step monitoring runs headless on the server.")
            return 0
        print("\nFAILED — session was not saved. Complete Facebook login and try again.")
        return 1
    except Exception as exc:
        logger.exception("Facebook login failed: %s", exc)
        print(f"\nERROR: {exc}")
        return 1
    finally:
        await fb.release_browser(None)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
