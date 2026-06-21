"""Playwright Chromium stored inside the project (install once via install-chromium.bat)."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
BROWSERS_DIR = BACKEND_ROOT / "playwright-browsers"


def configure_playwright_browsers_path() -> Path:
    """All Playwright browser downloads go to backend/playwright-browsers/."""
    BROWSERS_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(BROWSERS_DIR.resolve()))
    return BROWSERS_DIR


def chromium_executable() -> Path | None:
    configure_playwright_browsers_path()
    # Windows default
    for candidate in BROWSERS_DIR.glob("chromium-*/chrome-win64/chrome.exe"):
        if candidate.is_file():
            return candidate
    # Linux default (Playwright on Linux stores chrome binary under chrome-linux)
    for candidate in BROWSERS_DIR.glob("chromium-*/chrome-linux/chrome"):
        if candidate.is_file():
            return candidate
    # macOS default
    for candidate in BROWSERS_DIR.glob("chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"):
        if candidate.is_file():
            return candidate

    # Fallback: Playwright container sometimes installs to /ms-playwright
    ms_path = Path("/ms-playwright")
    if ms_path.exists():
        for candidate in ms_path.rglob("chrome*"):
            if candidate.is_file() and candidate.name.lower().startswith("chrome"):
                return candidate
    return None


def is_chromium_installed() -> bool:
    return chromium_executable() is not None
