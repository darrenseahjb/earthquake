from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from earthquake_bot.models import EarthquakeEvent


class UsgsClientError(RuntimeError):
    pass


class USGSClient:
    def __init__(self, feed_url: str, timeout_seconds: int = 20) -> None:
        self.feed_url = feed_url
        self.timeout_seconds = timeout_seconds

    def fetch_summary_feed(self) -> list[dict[str, Any]]:
        payload = self._get_json(self.feed_url)
        features = payload.get("features")
        if not isinstance(features, list):
            raise UsgsClientError("USGS summary feed did not contain a features list.")
        return features

    def fetch_detail(self, detail_url: str) -> EarthquakeEvent:
        payload = self._get_json(detail_url)
        return self._parse_detail(payload)

    def _get_json(self, url: str) -> dict[str, Any]:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "earthquake-monitoring-telegram-bot/0.1.0",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise UsgsClientError(f"USGS request failed with HTTP {exc.code} for {url}") from exc
        except URLError as exc:
            raise UsgsClientError(f"USGS request failed for {url}: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise UsgsClientError(f"USGS returned invalid JSON for {url}") from exc

    def _parse_detail(self, payload: dict[str, Any]) -> EarthquakeEvent:
        properties = payload.get("properties")
        geometry = payload.get("geometry")
        event_id = str(payload.get("id", "")).strip()

        if not event_id or not isinstance(properties, dict) or not isinstance(geometry, dict):
            raise UsgsClientError("USGS detail payload is missing required fields.")

        coordinates = geometry.get("coordinates") or [None, None, None]
        products = properties.get("products") or {}
        shakemap = self._extract_shakemap(products)

        return EarthquakeEvent(
            event_id=event_id,
            updated_ms=int(properties.get("updated", 0)),
            magnitude=self._to_float(properties.get("mag")),
            place=str(properties.get("place") or "Unknown location"),
            event_time=self._to_datetime(properties.get("time")),
            detail_url=str(properties.get("detail") or ""),
            event_url=str(properties.get("url") or ""),
            longitude=self._to_float(coordinates[0]),
            latitude=self._to_float(coordinates[1]),
            depth_km=self._to_float(coordinates[2]),
            tsunami=bool(properties.get("tsunami")),
            status=str(properties.get("status") or "unknown"),
            significance=self._to_int(properties.get("sig")),
            felt_reports=self._to_int(properties.get("felt")),
            alert_level=self._to_optional_str(properties.get("alert")),
            review_status=self._to_optional_str(properties.get("reviewstatus")),
            shakemap_url=shakemap["url"],
            max_mmi=shakemap["max_mmi"],
        )

    def _extract_shakemap(self, products: dict[str, Any]) -> dict[str, Any]:
        shakemap_entries = products.get("shakemap") or []
        if not shakemap_entries:
            return {"url": None, "max_mmi": None}

        first = shakemap_entries[0]
        contents = first.get("contents") or {}
        properties = first.get("properties") or {}

        preferred_url = None
        for key in (
            "download/intensity.jpg",
            "download/intensity_overlay.jpg",
            "download/pager.pdf",
        ):
            item = contents.get(key) or {}
            candidate = item.get("url")
            if candidate:
                preferred_url = str(candidate)
                break

        return {
            "url": preferred_url,
            "max_mmi": self._to_float(
                properties.get("maximum-likelihood-intensity") or properties.get("maxmmi")
            ),
        }

    def _to_datetime(self, timestamp_ms: Any) -> datetime:
        if timestamp_ms is None:
            return datetime.now(timezone.utc)
        return datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)

    def _to_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized or normalized.lower() in {"none", "null", "nan"}:
                return None
            value = normalized
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _to_int(self, value: Any) -> int | None:
        if value in (None, ""):
            return None
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized or normalized.lower() in {"none", "null", "nan"}:
                return None
            value = normalized
        try:
            return int(value)
        except (TypeError, ValueError):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return None

    def _to_optional_str(self, value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value)
