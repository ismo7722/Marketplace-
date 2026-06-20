"""Lightweight column migrations for existing databases (SQLite + PostgreSQL)."""
from sqlalchemy import inspect, text

from app.database import SessionLocal, engine

LEGACY_INTERVAL_PRESETS = {
    (120, 180),
    (120, 300),
    (180, 420),
    (300, 600),
    (600, 900),
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
                    "ADD COLUMN refresh_interval_min_seconds INTEGER NOT NULL DEFAULT 30"
                )
            )
        if "refresh_interval_max_seconds" not in existing:
            conn.execute(
                text(
                    "ALTER TABLE monitoring_settings "
                    "ADD COLUMN refresh_interval_max_seconds INTEGER NOT NULL DEFAULT 45"
                )
            )


def migrate_legacy_monitoring_intervals() -> None:
    """Move old slow reload presets to the new default check interval."""
    from app.models import MonitoringSetting

    db = SessionLocal()
    try:
        row = db.query(MonitoringSetting).first()
        if not row:
            return
        current = (row.refresh_interval_min_seconds, row.refresh_interval_max_seconds)
        if current in LEGACY_INTERVAL_PRESETS:
            row.refresh_interval_min_seconds = 30
            row.refresh_interval_max_seconds = 45
            row.refresh_interval_seconds = 45
            db.commit()
    finally:
        db.close()
