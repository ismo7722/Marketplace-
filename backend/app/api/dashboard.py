from datetime import datetime, timedelta, timezone

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
import csv
import io

from app.config import get_settings
from app.core.deps import get_current_user, require_admin
from app.database import get_db, with_db_retry
from app.db_async import run_sync
from app.models import (
    ActivityLog,
    Filter,
    Listing,
    ListingStatus,
    LogCategory,
    LogLevel,
    MonitoringSetting,
    Notification,
    NotificationRecipient,
    NotificationStatus,
    User,
    ApplicationSetting,
)
from app.schemas import (
    ActivityLogResponse,
    LogsBulkDelete,
    ApplicationSettingsUpdate,
    DashboardCharts,
    DashboardStats,
    ChartDataPoint,
    ManualScanResponse,
    MonitoringSettingsResponse,
    MonitoringSettingsUpdate,
    NotificationRecipientCreate,
    NotificationRecipientResponse,
    NotificationResponse,
    TestEmailRequest,
)
from app.services.email_service import email_service
from app.core.db_ready import require_db_ready
from app.services.log_service import log_activity, log_activity_isolated
from app.services.monitoring_runner import run_async_in_thread
from app.services.monitoring_service import get_smtp_settings, monitoring_service
from app.services.listing_query import matched_listings_query
from app.services.scan_schedule import (
    DEFAULT_SCAN_MAX_SECONDS,
    DEFAULT_SCAN_MIN_SECONDS,
    MIN_SCAN_INTERVAL_SECONDS,
    normalize_interval_bounds,
    schedule_next_scan,
)

router = APIRouter(tags=["Dashboard & Settings"])


@router.get("/dashboard/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    monitoring = db.query(MonitoringSetting).first()

    matched_q = matched_listings_query(db)

    return DashboardStats(
        total_listings=matched_q.count(),
        matched_listings=matched_q.count(),
        today_listings=matched_q.filter(Listing.found_at >= today_start).count(),
        notifications_sent=db.query(Notification).filter(Notification.status == NotificationStatus.SENT).count(),
        active_filters=db.query(Filter).filter(Filter.is_active == True).count(),
        system_status="active" if monitoring and monitoring.is_enabled else "idle",
        last_scan_at=monitoring.last_scan_at if monitoring else None,
        next_scan_at=monitoring.next_scan_at if monitoring else None,
        is_scanning=monitoring.is_enabled if monitoring else False,
        monitoring_enabled=monitoring.is_enabled if monitoring else False,
    )


@router.get("/dashboard/charts", response_model=DashboardCharts)
def get_dashboard_charts(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    days = 14
    now = datetime.now(timezone.utc)
    listings_per_day = []
    matches_per_day = []
    notifications_per_day = []

    for i in range(days - 1, -1, -1):
        day = (now - timedelta(days=i)).date()
        day_start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        listings_count = matched_listings_query(db).filter(
            Listing.found_at >= day_start, Listing.found_at < day_end
        ).count()
        matches_count = listings_count
        notif_count = db.query(Notification).filter(
            Notification.created_at >= day_start, Notification.created_at < day_end,
            Notification.status == NotificationStatus.SENT
        ).count()

        date_str = day.isoformat()
        listings_per_day.append(ChartDataPoint(date=date_str, count=listings_count))
        matches_per_day.append(ChartDataPoint(date=date_str, count=matches_count))
        notifications_per_day.append(ChartDataPoint(date=date_str, count=notif_count))

    return DashboardCharts(
        listings_per_day=listings_per_day,
        matches_per_day=matches_per_day,
        notifications_per_day=notifications_per_day,
    )


@router.get("/monitoring/settings", response_model=MonitoringSettingsResponse)
def get_monitoring_settings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    monitoring = db.query(MonitoringSetting).first()
    if not monitoring:
        monitoring = MonitoringSetting(
            refresh_interval_min_seconds=DEFAULT_SCAN_MIN_SECONDS,
            refresh_interval_max_seconds=DEFAULT_SCAN_MAX_SECONDS,
        )
        db.add(monitoring)
        db.commit()
        db.refresh(monitoring)
    min_s, max_s = normalize_interval_bounds(monitoring)
    if (
        monitoring.refresh_interval_min_seconds != min_s
        or monitoring.refresh_interval_max_seconds != max_s
    ):
        monitoring.refresh_interval_min_seconds = min_s
        monitoring.refresh_interval_max_seconds = max_s
        monitoring.refresh_interval_seconds = max_s
        db.commit()
        db.refresh(monitoring)
    return _monitoring_response(monitoring)


@router.put("/monitoring/settings", response_model=MonitoringSettingsResponse)
async def update_monitoring_settings(
    data: MonitoringSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    monitoring = db.query(MonitoringSetting).first()
    if not monitoring:
        monitoring = MonitoringSetting()
        db.add(monitoring)

    was_enabled = monitoring.is_enabled

    if data.is_enabled is not None:
        monitoring.is_enabled = data.is_enabled
        if data.is_enabled and not was_enabled:
            monitoring.next_scan_at = None
        elif not data.is_enabled:
            monitoring.next_scan_at = None

    if data.refresh_interval_min_seconds is not None:
        if data.refresh_interval_min_seconds < MIN_SCAN_INTERVAL_SECONDS:
            raise HTTPException(
                status_code=400,
                detail=f"Minimum delay is {MIN_SCAN_INTERVAL_SECONDS} seconds",
            )
        monitoring.refresh_interval_min_seconds = data.refresh_interval_min_seconds

    if data.refresh_interval_max_seconds is not None:
        if data.refresh_interval_max_seconds < MIN_SCAN_INTERVAL_SECONDS:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum delay is at least {MIN_SCAN_INTERVAL_SECONDS} seconds",
            )
        monitoring.refresh_interval_max_seconds = data.refresh_interval_max_seconds

    min_s, max_s = normalize_interval_bounds(monitoring)
    monitoring.refresh_interval_min_seconds = min_s
    monitoring.refresh_interval_max_seconds = max_s
    monitoring.refresh_interval_seconds = max_s

    if data.refresh_interval_seconds is not None:
        monitoring.refresh_interval_seconds = data.refresh_interval_seconds

    if (
        monitoring.is_enabled
        and not monitoring.is_scanning
        and monitoring.next_scan_at is not None
        and (
            data.refresh_interval_min_seconds is not None
            or data.refresh_interval_max_seconds is not None
        )
    ):
        schedule_next_scan(monitoring)

    db.commit()
    db.refresh(monitoring)

    return _monitoring_response(monitoring)


def _monitoring_response(monitoring: MonitoringSetting) -> MonitoringSettingsResponse:
    return MonitoringSettingsResponse(
        is_enabled=monitoring.is_enabled,
        refresh_interval_seconds=monitoring.refresh_interval_seconds,
        refresh_interval_min_seconds=monitoring.refresh_interval_min_seconds,
        refresh_interval_max_seconds=monitoring.refresh_interval_max_seconds,
        last_scan_at=monitoring.last_scan_at,
        next_scan_at=monitoring.next_scan_at,
        is_scanning=monitoring.is_enabled,
    )


def _launch_monitoring_background(force: bool = True) -> None:
    async def _run() -> None:
        try:
            await monitoring_service.run_scan(force=force)
        except Exception as exc:
            logging.getLogger(__name__).exception("Monitoring cycle failed: %s", exc)
            log_activity_isolated(
                LogCategory.ERROR, f"Monitoring cycle failed: {exc}",
                level=LogLevel.ERROR, source="monitor",
            )

    run_async_in_thread(_run, name="monitoring-scan")


@router.post("/monitoring/start", response_model=ManualScanResponse)
async def start_bot(
    _: None = Depends(require_db_ready),
    __: User = Depends(require_admin),
):
    """Start = ON. Runs full Facebook flow (headless on Render, visible on local PC)."""
    await monitoring_service.start_bot()
    log_activity_isolated(
        LogCategory.MONITORING,
        "Bot ON — starting Facebook monitoring (all stages)",
        source="monitor",
    )
    _launch_monitoring_background(force=True)
    return ManualScanResponse(status="started")


@router.post("/monitoring/stop")
async def stop_bot(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Stop = OFF. Closes Chromium and stops everything."""
    await monitoring_service.stop_bot()
    log_activity(db, LogCategory.MONITORING, "Bot OFF — stopped", source="monitor")
    return {"status": "stopped"}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    settings = db.query(ApplicationSetting).all()
    return {s.key: s.value for s in settings}


@router.put("/settings")
def update_settings(
    data: ApplicationSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    for key, value in data.settings.items():
        setting = db.query(ApplicationSetting).filter(ApplicationSetting.key == key).first()
        if setting:
            setting.value = value
        else:
            category = "notification" if key.startswith("smtp") else "general"
            db.add(ApplicationSetting(key=key, value=value, category=category))
    db.commit()
    return {"message": "Settings updated"}


@router.get("/settings/facebook-session")
def get_facebook_session_status_endpoint(_: User = Depends(get_current_user)):
    from app.services.facebook_session import get_facebook_session_status

    return get_facebook_session_status()


@router.post("/settings/clear-browser-session")
async def clear_browser_session(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Stop monitoring, close Chromium, delete session — next Start is fresh."""
    monitoring = db.query(MonitoringSetting).first()
    if monitoring:
        monitoring.is_enabled = False
        monitoring.is_scanning = False
        monitoring.next_scan_at = None
        db.commit()

    await monitoring_service.stop_bot()

    try:
        result = await asyncio.wait_for(
            monitoring_service.facebook.reset_completely(db),
            timeout=45,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Browser clear timed out — close the browser window manually and retry.") from exc
    log_activity(
        db,
        LogCategory.SYSTEM,
        "Clear browser — Chromium closed, session deleted, next Start is fresh",
        details=result,
        source="settings",
    )
    return {
        "message": "Browser closed and session wiped — next Start opens fresh Chromium",
        "cleared": result["session_file"] or result["profile_dir"],
        "details": result,
    }


@router.get("/notification-recipients", response_model=list[NotificationRecipientResponse])
def list_recipients(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(NotificationRecipient).order_by(desc(NotificationRecipient.created_at)).all()


@router.post("/notification-recipients", response_model=NotificationRecipientResponse)
def add_recipient(
    data: NotificationRecipientCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    existing = db.query(NotificationRecipient).filter(NotificationRecipient.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Recipient already exists")
    recipient = NotificationRecipient(**data.model_dump())
    db.add(recipient)
    db.commit()
    db.refresh(recipient)
    return recipient


@router.put("/notification-recipients/{recipient_id}", response_model=NotificationRecipientResponse)
def update_recipient(
    recipient_id: int,
    data: NotificationRecipientCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    recipient = db.query(NotificationRecipient).filter(NotificationRecipient.id == recipient_id).first()
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    recipient.email = data.email
    recipient.name = data.name
    recipient.is_active = data.is_active
    db.commit()
    db.refresh(recipient)
    return recipient


@router.delete("/notification-recipients/{recipient_id}")
def delete_recipient(
    recipient_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    recipient = db.query(NotificationRecipient).filter(NotificationRecipient.id == recipient_id).first()
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    db.delete(recipient)
    db.commit()
    return {"message": "Recipient deleted"}


@router.get("/notifications/email-status")
def email_delivery_status(_: User = Depends(require_admin)):
    """Which email provider is active — helps debug Render SMTP timeouts."""
    return email_service.email_status()


@router.post("/notifications/test-email")
async def send_test_email(
    data: TestEmailRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    from app.config import get_settings

    to_email = (data.email or get_settings().admin_email or "").strip()
    if not to_email or "@" not in to_email:
        raise HTTPException(status_code=400, detail="Enter a recipient email or set ADMIN_EMAIL in backend .env")

    smtp_config = get_smtp_settings(db)
    success, result = await email_service.send_test_email(to_email, smtp_config)
    if not success:
        raise HTTPException(status_code=400, detail=result)
    return {"message": result, "sent_to": to_email}


@router.get("/notifications", response_model=dict)
def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = db.query(Notification).order_by(desc(Notification.created_at))
    if status:
        query = query.filter(Notification.status == status)
    total = query.count()
    notifications = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for n in notifications:
        listing = db.query(Listing).filter(Listing.id == n.listing_id).first()
        items.append(NotificationResponse(
            id=n.id,
            listing_id=n.listing_id,
            recipient_email=n.recipient_email,
            status=n.status.value,
            delivery_result=n.delivery_result,
            sent_at=n.sent_at,
            created_at=n.created_at,
            listing_title=listing.title if listing else None,
        ))

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/logs", response_model=dict)
def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    category: str | None = None,
    level: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = db.query(ActivityLog).order_by(desc(ActivityLog.created_at))
    if category:
        query = query.filter(ActivityLog.category == category)
    if level:
        query = query.filter(ActivityLog.level == level)
    if search:
        query = query.filter(ActivityLog.message.ilike(f"%{search}%"))

    total = query.count()
    logs = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [ActivityLogResponse.model_validate(l) for l in logs],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.delete("/logs/all")
def delete_all_logs(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    deleted = db.query(ActivityLog).delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted, "message": f"Deleted {deleted} logs"}


@router.delete("/logs")
def delete_logs(
    data: LogsBulkDelete,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if not data.ids:
        raise HTTPException(status_code=400, detail="No log IDs provided")
    deleted = db.query(ActivityLog).filter(ActivityLog.id.in_(data.ids)).delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted, "message": f"Deleted {deleted} logs"}


@router.get("/logs/export/csv")
def export_logs_csv(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    logs = db.query(ActivityLog).order_by(desc(ActivityLog.created_at)).limit(5000).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Category", "Level", "Message", "Source", "Created At"])
    for log in logs:
        writer.writerow([log.id, log.category.value, log.level.value, log.message, log.source, log.created_at.isoformat()])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=logs.csv"},
    )
