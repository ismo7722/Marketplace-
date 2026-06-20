"""E2E verify: backend health → dashboard /login (API) → Start bot → poll scraper logs for URLs."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
ENV = dotenv_values(ROOT / ".env")
API_PORT = int(ENV.get("API_PORT") or 8000)
BASE = f"http://127.0.0.1:{API_PORT}"
ADMIN_EMAIL = ENV.get("ADMIN_EMAIL", "")
ADMIN_PASSWORD = ENV.get("ADMIN_PASSWORD", "")


def step(msg: str, **kw) -> None:
    extra = f" | {kw}" if kw else ""
    print(f"[VERIFY] {msg}{extra}", flush=True)


def wait_backend(timeout: float = 120.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{BASE}/health", timeout=5.0)
            data = r.json()
            if r.status_code == 200 and data.get("ready"):
                step("Backend ready", port=API_PORT)
                return True
            step("Backend starting...", status=r.status_code, ready=data.get("ready"))
        except Exception as exc:
            step("Waiting for backend...", error=str(exc)[:80])
        time.sleep(2)
    return False


def login() -> str:
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        step("FAIL — ADMIN_EMAIL / ADMIN_PASSWORD missing in backend/.env")
        sys.exit(1)
    step("Dashboard login (same as frontend /login)", email=ADMIN_EMAIL)
    r = httpx.post(
        f"{BASE}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30.0,
    )
    if r.status_code != 200:
        step("FAIL — dashboard login", status=r.status_code, body=r.text[:200])
        sys.exit(1)
    token = r.json()["access_token"]
    step("Dashboard login OK")
    return token


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def start_bot(token: str) -> None:
    step("POST /api/monitoring/start")
    r = httpx.post(
        f"{BASE}/api/monitoring/start",
        headers=auth_headers(token),
        timeout=30.0,
    )
    step("Bot start response", status=r.status_code, body=r.json() if r.status_code == 200 else r.text[:200])


def fetch_logs(token: str) -> list[dict]:
    r = httpx.get(
        f"{BASE}/api/logs",
        headers=auth_headers(token),
        params={"page": 1, "page_size": 50},
        timeout=15.0,
    )
    if r.status_code != 200:
        return []
    return r.json().get("items", [])


def main() -> int:
    step("=== E2E: frontend path = http://127.0.0.1:5173/login ===")
    step("=== Using .env admin creds for TEST only (not implemented in app) ===")

    if not wait_backend():
        step("FAIL — backend not ready. Run start-backend.bat first.")
        return 1

    try:
        httpx.get("http://127.0.0.1:5173", timeout=3.0)
        step("Frontend reachable at http://127.0.0.1:5173")
    except Exception:
        step("WARN — frontend not running on :5173 (start start-frontend.bat)")

    token = login()
    start_bot(token)

    seen: set[str] = set()
    url_hits: list[tuple[str, str, dict]] = []
    deadline = time.time() + 180

    step("Polling activity logs for bot URL stages (up to 3 min)...")
    while time.time() < deadline:
        for item in fetch_logs(token):
            msg = item.get("message") or ""
            details = item.get("details") or {}
            key = f"{item.get('created_at')}|{msg}"
            if key in seen:
                continue
            seen.add(key)

            if item.get("source") in ("facebook", "monitor", "scraper") or "Stage" in msg:
                step("LOG", message=msg[:120], details=details if details else None)

            for field in ("url", "marketplace_url", "navigation_seconds", "total_from_wait_start"):
                if field in details:
                    url_hits.append((msg, field, details))

            if "Monitoring cycle complete" in msg or "Stage 7/7" in msg:
                step("Scan cycle finished")
                break
        else:
            time.sleep(3)
            continue
        break

    step("--- URL flow summary ---")
    for msg, field, details in url_hits:
        if not isinstance(details, dict):
            continue
        if field in ("url", "marketplace_url"):
            step("URL", stage=msg[:60], **{field: details.get(field)})

    # Expected sequence check
    all_text = " ".join(m for m, _, _ in url_hits) + " ".join(seen)
    checks = [
        ("marketplace", "marketplace" in all_text.lower()),
        ("category/vehicles", "category/vehicles" in all_text.lower() or "vehicles" in all_text.lower()),
        ("5s wait", "5s" in all_text.lower() or "waiting 5" in all_text.lower()),
    ]
    step("--- Checks ---")
    ok = True
    for name, passed in checks:
        step(f"{'PASS' if passed else 'FAIL'} — {name}")
        ok = ok and passed

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
