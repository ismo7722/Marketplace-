import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.models import (
    ApplicationSetting,
    Filter,
    FilterKeyword,
    Listing,
    ListingStatus,
    LogCategory,
    LogLevel,
    MonitoringSetting,
    Notification,
    NotificationRecipient,
    NotificationStatus,
)
from app.services.browser_settings import ensure_visible_browser_setting, get_playwright_headless
from app.services.email_service import email_service
from app.services.log_service import log_activity, log_activity_isolated
from app.services.matching_engine import FilterCriteria, ListingData, MatchingEngine, listing_to_hash
from app.services.scan_schedule import schedule_next_scan
from app.sources.facebook import FacebookMarketplaceSource, FilterScrapeParams


def _parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else [str(parsed)]
    except json.JSONDecodeError:
        return [v.strip() for v in value.split(",") if v.strip()]


def filter_to_criteria(db_filter: Filter, db: Session) -> FilterCriteria:
    keywords = db.query(FilterKeyword).filter(FilterKeyword.filter_id == db_filter.id).all()
    include = [k.keyword for k in keywords if k.keyword_type == "include"]
    exclude = [k.keyword for k in keywords if k.keyword_type == "exclude"]
    return FilterCriteria(
        country=db_filter.country,
        city=db_filter.city,
        radius_km=db_filter.radius_km,
        brands=_parse_json_list(db_filter.brands),
        models=_parse_json_list(db_filter.models),
        fuel_types=_parse_json_list(db_filter.fuel_types),
        transmission_types=_parse_json_list(db_filter.transmission_types),
        price_min=db_filter.price_min,
        price_max=db_filter.price_max,
        mileage_min=db_filter.mileage_min,
        mileage_max=db_filter.mileage_max,
        year_min=db_filter.year_min,
        year_max=db_filter.year_max,
        include_keywords=include,
        exclude_keywords=exclude,
        min_match_score=db_filter.min_match_score,
    )


def filter_to_match_criteria(db_filter: Filter, db: Session) -> FilterCriteria:
    """Post-fetch matching — price already applied on Vehicles page."""
    criteria = filter_to_criteria(db_filter, db)
    criteria.price_min = None
    criteria.price_max = None
    return criteria


from app.config import get_settings
from app.database import SessionLocal


def get_smtp_settings(db: Session) -> dict:
    """SMTP always comes from backend .env — not from dashboard."""
    return get_settings().smtp_config_dict()


def get_notification_enabled(db: Session) -> bool:
    row = db.query(ApplicationSetting).filter(ApplicationSetting.key == "notifications_enabled").first()
    return row is None or row.value != "false"


from app.services.scan_control import (
    acquire_scan_or_wait,
    clear_scan_cancel,
    is_scan_busy,
    is_scan_cancelled,
    release_scan,
    request_scan_cancel,
    wait_until_scan_idle,
)

SCAN_MAX_SECONDS = 1800  # 30 min hard cap — always clears is_scanning after this


def is_monitoring_busy() -> bool:
    return is_scan_busy()


def reset_stale_scanning_flag(db: Session) -> None:
    """After restart: clear stale scan lock; keep monitoring ON if user had enabled it."""
    monitoring = db.query(MonitoringSetting).first()
    if not monitoring:
        return
    if not monitoring.is_scanning and not monitoring.is_enabled:
        return

    was_enabled = monitoring.is_enabled
    monitoring.is_scanning = False
    if was_enabled:
        monitoring.next_scan_at = None
    else:
        monitoring.is_enabled = False
        monitoring.next_scan_at = None
    db.commit()

    if was_enabled:
        log_activity(
            db,
            LogCategory.MONITORING,
            "Server restarted — monitoring still ON, resuming scan shortly",
            source="monitor",
        )
    else:
        log_activity(
            db,
            LogCategory.MONITORING,
            "Server restarted — monitoring OFF (press Start ON when ready)",
            source="monitor",
        )


def _clear_scanning_flag() -> None:
    db = SessionLocal()
    try:
        monitoring = db.query(MonitoringSetting).first()
        if monitoring and monitoring.is_scanning:
            monitoring.is_scanning = False
            db.commit()
    except Exception:
        pass
    finally:
        db.close()


def _is_monitoring_enabled() -> bool:
    db = SessionLocal()
    try:
        monitoring = db.query(MonitoringSetting).first()
        return bool(monitoring and monitoring.is_enabled)
    except Exception:
        return False
    finally:
        db.close()


def _set_monitoring_enabled(enabled: bool) -> None:
    db = SessionLocal()
    try:
        monitoring = db.query(MonitoringSetting).first()
        if monitoring:
            monitoring.is_enabled = enabled
            monitoring.is_scanning = False
            if not enabled:
                monitoring.next_scan_at = None
            db.commit()
    except Exception:
        pass
    finally:
        db.close()


class MonitoringService:
    def __init__(self):
        self.matching_engine = MatchingEngine()
        self.facebook = FacebookMarketplaceSource()

    async def stop_bot(self) -> None:
        """Stop = OFF. Cancel everything, close Chromium, clear flags."""
        _set_monitoring_enabled(False)
        request_scan_cancel()
        try:
            await asyncio.wait_for(
                self.facebook.save_session_and_release(),
                timeout=20,
            )
        except Exception:
            pass
        _clear_scanning_flag()
        await asyncio.to_thread(wait_until_scan_idle, 12.0)

    async def start_bot(self) -> None:
        """Start = ON. Stop any leftover run, then enable."""
        await self.stop_bot()
        clear_scan_cancel()
        db = SessionLocal()
        try:
            monitoring = db.query(MonitoringSetting).first()
            if not monitoring:
                monitoring = MonitoringSetting()
                db.add(monitoring)
            monitoring.is_enabled = True
            monitoring.is_scanning = False
            monitoring.next_scan_at = None
            db.commit()
        finally:
            db.close()

    async def run_scan(self, db: Session | None = None, force: bool = False) -> dict:
        if not _is_monitoring_enabled() and not force:
            return {"status": "off", "processed": 0, "matched": 0, "notified": 0, "duplicates": 0, "errors": 0}

        if not acquire_scan_or_wait(timeout_seconds=15.0):
            logger.warning("Could not acquire scan lock")
            return {"status": "off", "processed": 0, "matched": 0, "notified": 0, "duplicates": 0, "errors": 0}

        clear_scan_cancel()
        try:
            own_db = db is None
            if own_db:
                db = SessionLocal()
            try:
                try:
                    return await asyncio.wait_for(
                        self._run_scan_locked(db, force),
                        timeout=SCAN_MAX_SECONDS,
                    )
                except asyncio.TimeoutError:
                    logger.error("Monitoring scan exceeded %ss — forcing stop", SCAN_MAX_SECONDS)
                    log_activity_isolated(
                        LogCategory.ERROR,
                        f"Monitoring timed out after {SCAN_MAX_SECONDS // 60} minutes — stopped",
                        level=LogLevel.ERROR,
                        source="monitor",
                    )
                    await self.stop_bot()
                    return {
                        "status": "timeout",
                        "processed": 0,
                        "matched": 0,
                        "notified": 0,
                        "duplicates": 0,
                        "errors": 1,
                    }
            finally:
                if own_db:
                    try:
                        db.close()
                    except Exception:
                        pass
        finally:
            release_scan()

    async def _run_scan_locked(self, db: Session, force: bool = False) -> dict:
        monitoring = db.query(MonitoringSetting).first()
        if not monitoring:
            monitoring = MonitoringSetting()
            db.add(monitoring)
            db.commit()
            db.refresh(monitoring)

        if not monitoring.is_enabled and not force:
            return {"status": "off", "processed": 0, "matched": 0, "notified": 0, "duplicates": 0, "errors": 0}

        if is_scan_cancelled() or not _is_monitoring_enabled():
            return {"status": "off", "processed": 0, "matched": 0, "notified": 0, "duplicates": 0, "errors": 0}

        monitoring.is_scanning = True
        db.commit()

        stats = {"processed": 0, "matched": 0, "notified": 0, "duplicates": 0, "errors": 0, "login_required": False}
        if force:
            log_activity(db, LogCategory.MONITORING, "Bot ON — monitoring started", source="monitor")
        else:
            log_activity(
                db,
                LogCategory.MONITORING,
                "Monitoring cycle — scroll, read listings and match filters",
                source="monitor",
            )
        db.commit()

        try:
            return await self._execute_scan(db, monitoring, force, stats)
        finally:
            cleanup_db = SessionLocal()
            try:
                monitoring = cleanup_db.query(MonitoringSetting).first()
                if monitoring and monitoring.is_scanning:
                    monitoring.is_scanning = False
                    cleanup_db.commit()
            finally:
                cleanup_db.close()
            try:
                db.close()
            except Exception:
                pass

    async def _execute_scan(self, db: Session, monitoring: MonitoringSetting, force: bool, stats: dict) -> dict:
        headless_mode = get_playwright_headless(db)
        db.commit()
        try:
            active_filters = db.query(Filter).filter(Filter.is_active == True).all()
            db.commit()

            for db_filter in active_filters:
                if is_scan_cancelled() or not _is_monitoring_enabled():
                    break

                filter_name = db_filter.name
                criteria = filter_to_match_criteria(db_filter, db)
                db.commit()

                log_activity_isolated(
                    LogCategory.MONITORING,
                    f"Matching against filter: {filter_name}",
                    details={
                        "brands": criteria.brands,
                        "models": criteria.models,
                        "fuel_types": criteria.fuel_types,
                        "transmission_types": criteria.transmission_types,
                        "mileage_min": criteria.mileage_min,
                        "mileage_max": criteria.mileage_max,
                        "year_min": criteria.year_min,
                        "year_max": criteria.year_max,
                        "rule": "ALL set fields must match (AND); multiple values in one field = any (OR)",
                    },
                    source="monitor",
                )

                filter_id = db_filter.id
                scrape_params = FilterScrapeParams.from_filter(db_filter)
                db.commit()
                try:
                    db.close()
                except Exception:
                    pass

                try:
                    raw_listings = await self.facebook.run_filter_scrape(
                        None, scrape_params, criteria=criteria
                    )
                except Exception as exc:
                    from app.services.facebook_errors import FacebookLoginRequiredError

                    db = SessionLocal()
                    if isinstance(exc, FacebookLoginRequiredError):
                        log_activity(
                            db,
                            LogCategory.MONITORING,
                            str(exc),
                            level=LogLevel.WARNING,
                            source="monitor",
                        )
                        stats["login_required"] = True
                    else:
                        stats["errors"] += 1
                        log_activity(
                            db,
                            LogCategory.MONITORING,
                            f"Scan issue for {filter_name} — will retry",
                            level=LogLevel.WARNING,
                            details={"error": str(exc)},
                            source="monitor",
                        )
                    db.commit()
                    db.close()
                    continue

                db = SessionLocal()
                db_filter = db.query(Filter).filter(Filter.id == filter_id).first()
                if not db_filter:
                    continue
                criteria = filter_to_match_criteria(db_filter, db)

                log_activity(
                    db, LogCategory.MONITORING,
                    f"Filter matching — {filter_name}: {len(raw_listings)} listing(s) from Stage 5",
                    details={"filter": db_filter.name, "checked_in_detail": len(raw_listings)},
                    source="monitor",
                )

                skipped_non_match = 0
                filter_matched = 0
                filter_duplicates = 0
                for raw in raw_listings:
                    stats["processed"] += 1
                    content_hash = listing_to_hash(raw)

                    existing = db.query(Listing).filter(
                        (Listing.external_id == raw.external_id) | (Listing.content_hash == content_hash)
                    ).first()

                    if existing:
                        stats["duplicates"] += 1
                        filter_duplicates += 1
                        continue

                    is_match, match_result = self.matching_engine.is_full_match(raw, criteria)
                    if not is_match:
                        skipped_non_match += 1
                        continue

                    stats["matched"] += 1
                    filter_matched += 1
                    listing = self._save_listing(
                        db, raw, content_hash, match_result.score, db_filter.id,
                        match_result.details, ListingStatus.MATCHED, False
                    )

                    if get_notification_enabled(db):
                        log_activity(
                            db, LogCategory.NOTIFICATION,
                            f"Sending alert email: {raw.title[:60]}",
                            details={"score": match_result.score, "listing_id": listing.id},
                            source="monitor",
                        )
                        notified = await self._send_notifications(
                            db, listing, raw, db_filter.name, match_result.details
                        )
                        if notified:
                            stats["notified"] += notified
                            listing.status = ListingStatus.NOTIFIED
                            listing.notification_sent = True
                            db.commit()

                log_activity(
                    db,
                    LogCategory.MONITORING,
                    (
                        f"Filter '{filter_name}' results — "
                        f"{filter_matched} matched and saved, "
                        f"{filter_duplicates} already in database, "
                        f"{skipped_non_match} skipped (did not match criteria)"
                    ),
                    details={
                        "filter": db_filter.name,
                        "matched": filter_matched,
                        "duplicates": filter_duplicates,
                        "skipped": skipped_non_match,
                    },
                    source="monitor",
                )

            now = datetime.now(timezone.utc)
            monitoring = db.query(MonitoringSetting).first()
            if monitoring:
                monitoring.last_scan_at = now
                if monitoring.is_enabled and not is_scan_cancelled():
                    if stats.get("login_required"):
                        monitoring.next_scan_at = now + timedelta(minutes=15)
                        log_activity(
                            db,
                            LogCategory.MONITORING,
                            "Waiting for Facebook login — run login-facebook.bat (check email), then Stop → Start",
                            source="monitor",
                        )
                    elif stats["errors"] > 0 and stats["processed"] == 0:
                        monitoring.next_scan_at = now + timedelta(minutes=2)
                        log_activity(
                            db, LogCategory.MONITORING,
                            "Scan issue — retry in 2 minutes",
                            level=LogLevel.WARNING,
                            source="monitor",
                        )
                    else:
                        scheduled = schedule_next_scan(monitoring, now)
                        min_s, max_s = scheduled.interval_min_seconds, scheduled.interval_max_seconds
                        delay_sec = scheduled.delay_seconds
                        log_activity(
                            db,
                            LogCategory.MONITORING,
                            (
                                f"Cycle complete — {stats['processed']} checked, "
                                f"{stats['matched']} matched, "
                                f"{stats['duplicates']} already seen, "
                                f"{stats['notified']} alert(s) sent"
                            ),
                            details={
                                "processed": stats["processed"],
                                "matched": stats["matched"],
                                "duplicates": stats["duplicates"],
                                "notified": stats["notified"],
                                "errors": stats["errors"],
                            },
                            source="monitor",
                        )
                        log_activity(
                            db,
                            LogCategory.MONITORING,
                            (
                                f"Waiting {delay_sec}s before next scroll and check "
                                f"(random from {min_s}–{max_s}s interval)"
                            ),
                            details={
                                "delay_seconds": delay_sec,
                                "interval_min_seconds": min_s,
                                "interval_max_seconds": max_s,
                                "next_at": scheduled.next_at.isoformat(),
                            },
                            source="monitor",
                        )
                else:
                    monitoring.is_enabled = False
                    monitoring.next_scan_at = None
                monitoring.is_scanning = False
                db.commit()

            if not _is_monitoring_enabled():
                await self.facebook.release_browser(db, keep_open=False)
                log_activity(db, LogCategory.MONITORING, "Bot stopped", source="monitor")
                return {"status": "off", **stats}

            if stats.get("login_required"):
                await self.facebook.release_browser(db, keep_open=False)
                return {"status": "login_required", **stats}

            await self.facebook.release_browser(db, keep_open=True)
            return {"status": "completed", **stats}

        except Exception as exc:
            logger.exception("Monitoring cycle failed: %s", exc)
            try:
                db.rollback()
            except Exception:
                pass
            await self.facebook.release_browser(db, keep_open=not headless_mode)
            log_activity_isolated(
                LogCategory.ERROR, f"Monitoring failed: {exc}", level=LogLevel.ERROR, source="monitor",
            )
            stats["errors"] += 1
            return {"status": "failed", **stats}

    def _save_listing(
        self, db: Session, raw: ListingData, content_hash: str, score: float,
        filter_id: int, details: dict, status: ListingStatus, is_duplicate: bool
    ) -> Listing:
        listing = Listing(
            external_id=raw.external_id,
            source=raw.source,
            url=raw.url,
            content_hash=content_hash,
            title=raw.title,
            price=raw.price,
            currency=raw.currency,
            mileage=raw.mileage,
            year=raw.year,
            brand=raw.brand,
            model=raw.model,
            fuel_type=raw.fuel_type,
            transmission=raw.transmission,
            description=raw.description,
            location=raw.location,
            seller_name=raw.seller_name,
            images=json.dumps(raw.images),
            posted_time=raw.posted_time,
            match_score=score,
            status=status,
            filter_id=filter_id,
            match_details=json.dumps(details),
            is_duplicate=is_duplicate,
        )
        db.add(listing)
        db.commit()
        db.refresh(listing)
        return listing

    async def _send_notifications(
        self, db: Session, listing: Listing, raw: ListingData, filter_name: str, match_details: dict
    ) -> int:
        recipients = db.query(NotificationRecipient).filter(NotificationRecipient.is_active == True).all()
        if not recipients:
            return 0

        smtp_config = get_smtp_settings(db)
        images = json.loads(listing.images) if listing.images else []
        sent_count = 0

        score_breakdown = ", ".join(
            f"{k}: {int(v)}%" for k, v in sorted(match_details.items()) if v is not None
        )

        for recipient in recipients:
            notification = Notification(
                listing_id=listing.id,
                recipient_email=recipient.email,
                status=NotificationStatus.PENDING,
            )
            db.add(notification)
            db.commit()
            db.refresh(notification)

            success, result = await email_service.send_listing_notification(
                recipient.email,
                {
                    "title": listing.title,
                    "price": listing.price or "N/A",
                    "currency": listing.currency,
                    "mileage": listing.mileage,
                    "year": listing.year,
                    "brand": listing.brand or raw.brand,
                    "model": listing.model or raw.model,
                    "fuel_type": listing.fuel_type or raw.fuel_type,
                    "transmission": listing.transmission or raw.transmission,
                    "location": listing.location or "Unknown",
                    "posted_time": listing.posted_time or "Recently",
                    "match_score": listing.match_score,
                    "filter_name": filter_name,
                    "score_breakdown": score_breakdown,
                    "description": (raw.description or "")[:300] or None,
                    "listing_url": listing.url,
                    "image_url": images[0] if images else None,
                },
                smtp_config,
            )

            notification.status = NotificationStatus.SENT if success else NotificationStatus.FAILED
            notification.delivery_result = result
            notification.sent_at = datetime.now(timezone.utc) if success else None
            db.commit()

            if success:
                sent_count += 1

            log_activity(
                db,
                LogCategory.NOTIFICATION,
                f"Notification {'sent' if success else 'failed'} to {recipient.email}",
                level=LogLevel.INFO if success else LogLevel.ERROR,
                details={"listing_id": listing.id, "result": result},
            )

        return sent_count


monitoring_service = MonitoringService()
