from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earthquake_bot.config import Config
from earthquake_bot.models import EarthquakeEvent
from earthquake_bot.service import EarthquakeBotService
from earthquake_bot.storage import Storage
from earthquake_bot.usgs import USGSClient


class StubTelegramClient:
    def send_message(self, *args, **kwargs) -> None:
        return None


class StubUsgsClient:
    def __init__(self, event: EarthquakeEvent) -> None:
        self.event = event

    def fetch_summary_feed(self) -> list[dict[str, object]]:
        return [
            {
                "id": "bad-event",
                "properties": {"updated": 1, "detail": "https://example.com/bad"},
            },
            {
                "id": self.event.event_id,
                "properties": {"updated": self.event.updated_ms, "detail": self.event.detail_url},
            },
        ]

    def fetch_detail(self, detail_url: str) -> EarthquakeEvent:
        if detail_url.endswith("/bad"):
            raise ValueError("bad upstream payload")
        return self.event


class UsgsClientTests(unittest.TestCase):
    def test_to_float_treats_string_none_as_missing(self) -> None:
        client = USGSClient("https://example.com/feed")
        self.assertIsNone(client._to_float("None"))
        self.assertIsNone(client._to_float(" null "))
        self.assertEqual(client._to_float("4.5"), 4.5)

    def test_to_int_treats_string_none_as_missing(self) -> None:
        client = USGSClient("https://example.com/feed")
        self.assertIsNone(client._to_int("None"))
        self.assertIsNone(client._to_int(" nan "))
        self.assertEqual(client._to_int("7"), 7)


class ServiceSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "bot.sqlite3"
        self.config = Config(
            telegram_bot_token="test-token",
            usgs_feed_url="https://example.com/feed",
            usgs_poll_seconds=60,
            default_min_magnitude=5.0,
            database_path=database_path,
            telegram_long_poll_seconds=10,
        )
        self.storage = Storage(database_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_sync_earthquakes_skips_bad_detail_and_continues(self) -> None:
        good_event = EarthquakeEvent(
            event_id="good-event",
            updated_ms=2,
            magnitude=5.2,
            place="100 km E of Test, Japan",
            event_time=datetime(2026, 3, 30, 9, 0, tzinfo=timezone.utc),
            detail_url="https://example.com/good",
            event_url="https://example.com/event/good",
            latitude=1.0,
            longitude=2.0,
            depth_km=10.0,
            tsunami=False,
            status="reviewed",
            significance=500,
            felt_reports=3,
            alert_level=None,
            review_status="reviewed",
            shakemap_url=None,
            max_mmi=None,
        )
        service = EarthquakeBotService(
            self.config,
            self.storage,
            StubUsgsClient(good_event),
            StubTelegramClient(),
        )

        changed = service.sync_earthquakes()

        self.assertEqual(changed, 1)
        latest = self.storage.get_latest_events(limit=1)
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0].event_id, "good-event")


if __name__ == "__main__":
    unittest.main()
