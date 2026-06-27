"""Random delay between monitoring cycles."""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.models import MonitoringSetting

logger = logging.getLogger(__name__)

MIN_SCAN_INTERVAL_SECONDS = 90
DEFAULT_SCAN_MIN_SECONDS = 90
DEFAULT_SCAN_MAX_SECONDS = 120


@dataclass(frozen=True)
class ScheduledScan:
    next_at: datetime
    delay_seconds: int
    interval_min_seconds: int
    interval_max_seconds: int


def normalize_interval_bounds(monitoring: MonitoringSetting) -> tuple[int, int]:
    min_s = monitoring.refresh_interval_min_seconds or DEFAULT_SCAN_MIN_SECONDS
    max_s = monitoring.refresh_interval_max_seconds or DEFAULT_SCAN_MAX_SECONDS
    if min_s > max_s:
        min_s, max_s = max_s, min_s
    min_s = max(MIN_SCAN_INTERVAL_SECONDS, min_s)
    max_s = max(min_s, max_s)
    return min_s, max_s


def random_delay_seconds(monitoring: MonitoringSetting) -> int:
    min_s, max_s = normalize_interval_bounds(monitoring)
    return random.randint(min_s, max_s)


def schedule_next_scan(monitoring: MonitoringSetting, from_time: datetime | None = None) -> ScheduledScan:
    base = from_time or datetime.now(timezone.utc)
    min_s, max_s = normalize_interval_bounds(monitoring)
    delay = random.randint(min_s, max_s)
    monitoring.next_scan_at = base + timedelta(seconds=delay)
    logger.info(
        "Next monitoring cycle in %d sec (interval %d–%d s, at %s)",
        delay,
        min_s,
        max_s,
        monitoring.next_scan_at.isoformat(),
    )
    return ScheduledScan(
        next_at=monitoring.next_scan_at,
        delay_seconds=delay,
        interval_min_seconds=min_s,
        interval_max_seconds=max_s,
    )
