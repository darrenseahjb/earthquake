from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class EarthquakeEvent:
    event_id: str
    updated_ms: int
    magnitude: float | None
    place: str
    event_time: datetime
    detail_url: str
    event_url: str
    latitude: float | None
    longitude: float | None
    depth_km: float | None
    tsunami: bool
    status: str
    significance: int | None
    felt_reports: int | None
    alert_level: str | None
    review_status: str | None
    shakemap_url: str | None
    max_mmi: float | None


@dataclass(slots=True)
class Subscription:
    chat_id: int
    min_magnitude: float
    region_filter: str | None
    enabled: bool
    updated_at: datetime


@dataclass(slots=True)
class OutboundMessage:
    message_id: int
    chat_id: int
    message_kind: str
    text: str
    parse_mode: str | None
    reply_markup: dict[str, Any] | None
    media: bytes | None
    media_filename: str | None
    category: str
    dedupe_key: str | None
    attempt_count: int
    next_attempt_at: datetime
    leased_until: datetime | None
    created_at: datetime
    updated_at: datetime
    sent_at: datetime | None
    last_error: str | None
