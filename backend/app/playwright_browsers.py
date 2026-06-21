"""Playwright Chromium — local folder or Playwright Docker image on Render."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from app.config import is_cloud_host

BACKEND_ROOT = Path(__file__).resolve().parent.parent
BROWSERS_DIR = BACKEND_ROOT / "playwright-browsers"


def configure_playwright_browsers_path() -> Path:
    BROWSERS_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(BROWSERS_DIR.resolve()))
    return BROWSERS_DIR


def _glob_chromium_binary() -> Path | None:
    configure_playwright_browsers_path()
    patterns = (
        "chromium-*/chrome-win64/chrome.exe",
        "chromium-*/chrome-linux/chrome",
        "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
        "chromium-*/chrome",
    )
    for pattern in patterns:
        for candidate in BROWSERS_DIR.glob(pattern):
            if candidate.is_file():
                return candidate

    ms_path = Path("/ms-playwright")
    if ms_path.exists():
        for pattern in ("chromium-*/chrome-linux/chrome", "chromium-*/chrome"):
            for candidate in ms_path.glob(pattern):
                if candidate.is_file():
                    return candidate
        for candidate in ms_path.rglob("chrome*"):
            if candidate.is_file() and candidate.name.lower().startswith("chrome"):
                return candidate
    return None


def chromium_executable() -> Path | None:
    return _glob_chromium_binary()


def is_chromium_installed() -> bool:
    if chromium_executable() is not None:
        return True
    if is_cloud_host() or Path("/ms-playwright").exists():
        return True
    return sys.platform == "win32" and (BROWSERS_DIR / "chromium-headless-shell-win64").exists()
