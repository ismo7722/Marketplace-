"""Blocking startup steps — run in a thread with a timeout from main lifespan."""
from __future__ import annotations

import logging

from sqlalchemy import inspect

from app.config import Settings
from app.database import Base, SessionLocal, engine, invalidate_pool
from app.database_migrate import ensure_monitoring_interval_columns, migrate_legacy_monitoring_intervals
from app.seeds.seed_data import seed_database
from app.services.browser_settings import ensure_visible_browser_setting
from app.services.monitoring_service import reset_stale_scanning_flag

logger = logging.getLogger(__name__)


def _tables_present() -> bool:
    inspector = inspect(engine)
    return inspector.has_table("users") and inspector.has_table("monitoring_settings")


def run_blocking_startup(settings: Settings) -> None:
    logger.info("Startup: connecting to database...")
    if not _tables_present():
        logger.info("Startup: creating database tables...")
        Base.metadata.create_all(bind=engine)
    else:
        logger.info("Startup: database tables already exist")

    logger.info("Startup: applying migrations...")
    ensure_monitoring_interval_columns()
    migrate_legacy_monitoring_intervals()

    db = SessionLocal()
    try:
        logger.info("Startup: seeding defaults...")
        ensure_visible_browser_setting(db)
        reset_stale_scanning_flag(db)
        seed_database(db, settings.admin_email, settings.admin_password)
        logger.info("Startup: database ready")
    finally:
        db.close()
