"""Lightweight column migrations for existing databases (SQLite + PostgreSQL)."""
from sqlalchemy import inspect, text

from app.database import SessionLocal, engine
from app.services.scan_schedule import DEFAULT_SCAN_MAX_SECONDS, DEFAULT_SCAN_MIN_SECONDS

# Old fast intervals (unsafe for 24/7 Facebook monitoring).
UNSAFE_FAST_INTERVALS = {
    (30, 45),
    (30, 60),
    (45, 90),
    (60, 120),
}


def ensure_monitoring_interval_columns() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("monitoring_settings"):
        return
    existing = {c["name"] for c in inspector.get_columns("monitoring_settings")}
    with engine.begin() as conn:
        if "refresh_interval_min_seconds" not in existing:
            conn.execute(
                text(
                    "ALTER TABLE monitoring_settings "
                    f"ADD COLUMN refresh_interval_min_seconds INTEGER NOT NULL DEFAULT {DEFAULT_SCAN_MIN_SECONDS}"
                )
            )
        if "refresh_interval_max_seconds" not in existing:
            conn.execute(
                text(
                    "ALTER TABLE monitoring_settings "
                    f"ADD COLUMN refresh_interval_max_seconds INTEGER NOT NULL DEFAULT {DEFAULT_SCAN_MAX_SECONDS}"
                )
            )


def migrate_legacy_monitoring_intervals() -> None:
    """Bump old sub-90s intervals to the safe default (90–120 s)."""
    from app.models import MonitoringSetting

    db = SessionLocal()
    try:
        row = db.query(MonitoringSetting).first()
        if not row:
            return
        current = (row.refresh_interval_min_seconds, row.refresh_interval_max_seconds)
        if row.refresh_interval_min_seconds < DEFAULT_SCAN_MIN_SECONDS or current in UNSAFE_FAST_INTERVALS:
            row.refresh_interval_min_seconds = DEFAULT_SCAN_MIN_SECONDS
            row.refresh_interval_max_seconds = DEFAULT_SCAN_MAX_SECONDS
            row.refresh_interval_seconds = DEFAULT_SCAN_MAX_SECONDS
            db.commit()
    finally:
        db.close()
