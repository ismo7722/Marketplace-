"""One-time Facebook login on your PC — saves session to database for Render headless bot."""
from __future__ import annotations

import asyncio
import logging
import os
import sys

os.environ["FACEBOOK_LOGIN_MODE"] = "1"

from app.config import get_settings
from app.services.facebook_session import get_facebook_session_status, persist_session_file_to_db
from app.sources.facebook import FacebookMarketplaceSource
from app.startup_db import run_blocking_startup

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
            print("Dashboard: Stop → Start — all 7 stages will run headless on the server.")
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
