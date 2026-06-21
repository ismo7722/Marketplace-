import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db_async import run_sync
from app.services.monitoring_runner import run_async_in_thread
from app.services.monitoring_service import monitoring_service

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
_monitor_lock = asyncio.Lock()
TICK_SECONDS = 60
_SCHEDULER_DB_TIMEOUT = 8.0


def _load_monitoring_row():
    from app.database import SessionLocal
    from app.models import MonitoringSetting

    db = SessionLocal()
    try:
        return db.query(MonitoringSetting).first()
    finally:
        db.close()


def _read_monitoring_enabled() -> bool:
    monitoring = _load_monitoring_row()
    return bool(monitoring and monitoring.is_enabled)


async def check_monitoring_due():
    if _monitor_lock.locked():
        return

    from app.services.monitoring_service import is_monitoring_busy

    if is_monitoring_busy():
        return

    async with _monitor_lock:
        try:
            monitoring = await run_sync(_load_monitoring_row, timeout=_SCHEDULER_DB_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("Scheduler: database check timed out")
            return
        except Exception as exc:
            logger.warning("Scheduler: database check failed: %s", exc)
            return

        if not monitoring or not monitoring.is_enabled:
            return
        if monitoring.is_scanning:
            return
        if is_monitoring_busy():
            return

        now = datetime.now(timezone.utc)
        if monitoring.next_scan_at is not None and now < monitoring.next_scan_at:
            return

        logger.info(
            "Monitoring interval reached — reloading /vehicles (due %s)",
            monitoring.next_scan_at.isoformat() if monitoring.next_scan_at else "now",
        )

        async def _run_scheduled_scan() -> None:
            try:
                await monitoring_service.run_scan()
            except Exception as exc:
                logger.exception("Scheduled monitoring scan failed: %s", exc)

        run_async_in_thread(_run_scheduled_scan, name="monitoring-scheduled")


async def resume_monitoring_on_startup():
    await asyncio.sleep(3)
    try:
        monitoring = await run_sync(_load_monitoring_row, timeout=_SCHEDULER_DB_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("Startup: monitoring settings timed out")
        return
    except Exception as exc:
        logger.warning("Startup: monitoring settings failed: %s", exc)
        return

    if monitoring and monitoring.is_enabled and not monitoring.is_scanning:
        if monitoring.next_scan_at is None and not monitoring_service.facebook.has_live_browser():
            logger.info("Monitoring was ON — resuming after server restart")

            async def _run_startup_scan() -> None:
                try:
                    await monitoring_service.run_scan()
                except Exception as exc:
                    logger.exception("Startup monitoring scan failed: %s", exc)

            run_async_in_thread(_run_startup_scan, name="monitoring-startup")
        elif monitoring.next_scan_at is None:
            logger.info("Monitoring ON — browser already open, waiting for next cycle")
        else:
            logger.info("Monitoring ON — next cycle already scheduled")
    elif monitoring and monitoring.is_enabled:
        logger.info("Monitoring ON — cycle already in progress")
    else:
        logger.info("Monitoring OFF — press Start on Dashboard")


def start_scheduler():
    try:
        is_enabled = _read_monitoring_enabled()
    except Exception as exc:
        logger.warning("Could not read monitoring settings for scheduler: %s", exc)
        is_enabled = False

    if not scheduler.running:
        scheduler.add_job(
            check_monitoring_due,
            trigger=IntervalTrigger(seconds=TICK_SECONDS),
            id="monitoring_check",
            replace_existing=True,
            max_instances=1,
        )
        scheduler.start()
        state = "ON" if is_enabled else "OFF — press Start"
        logger.info(
            "Scheduler started — checks every %ds for next monitoring cycle (%s)",
            TICK_SECONDS,
            state,
        )


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
