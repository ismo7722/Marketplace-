"""Quick sanity checks for Facebook monitoring flow (no browser)."""
from __future__ import annotations

import sys

from app.services.facebook_flow import (
    VEHICLES_CATEGORY_URL,
    vehicles_search_url,
)


class FakePage:
    def __init__(self, url: str) -> None:
        self.url = url


def main() -> int:
    from app.services.facebook_flow import _is_on_vehicles_page

    checks = []

    zurich_fallback = vehicles_search_url("Zurich")
    expected = (
        "https://www.facebook.com/marketplace/zurich/search/"
        "?category_id=546583916084032&query=Vehicles&referral_ui_component=category_menu_item"
    )
    checks.append(("Zurich fallback URL", zurich_fallback == expected))

    checks.append(
        (
            "Primary vehicles URL used by bot",
            VEHICLES_CATEGORY_URL == "https://www.facebook.com/marketplace/category/vehicles",
        )
    )

    checks.append(
        (
            "category/vehicles detected",
            _is_on_vehicles_page(FakePage("https://www.facebook.com/marketplace/category/vehicles")),
        )
    )
    checks.append(
        (
            "city search detected",
            _is_on_vehicles_page(FakePage(zurich_fallback)),
        )
    )
    checks.append(
        (
            "marketplace home NOT vehicles",
            not _is_on_vehicles_page(FakePage("https://www.facebook.com/marketplace/")),
        )
    )

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")

    if failed:
        print(f"\n{len(failed)} check(s) failed")
        return 1
    print("\nAll flow checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
