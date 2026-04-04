from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earthquake_bot.models import EarthquakeEvent
from earthquake_bot.storage import Storage


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "bot.sqlite3"
        self.storage = Storage(self.database_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_get_known_updated_ms_map_batches_existing_events(self) -> None:
        first = EarthquakeEvent(
            event_id="evt-1",
            updated_ms=10,
            magnitude=4.1,
            place="Test Place 1",
            event_time=datetime(2026, 3, 30, 9, 0, tzinfo=timezone.utc),
            detail_url="https://example.com/detail/1",
            event_url="https://example.com/event/1",
            latitude=1.0,
            longitude=2.0,
            depth_km=3.0,
            tsunami=False,
            status="reviewed",
            significance=100,
            felt_reports=1,
            alert_level=None,
            review_status="reviewed",
            shakemap_url=None,
            max_mmi=None,
        )
        second = EarthquakeEvent(
            event_id="evt-2",
            updated_ms=20,
            magnitude=5.2,
            place="Test Place 2",
            event_time=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
            detail_url="https://example.com/detail/2",
            event_url="https://example.com/event/2",
            latitude=4.0,
            longitude=5.0,
            depth_km=6.0,
            tsunami=False,
            status="reviewed",
            significance=200,
            felt_reports=2,
            alert_level="yellow",
            review_status="reviewed",
            shakemap_url=None,
            max_mmi=None,
        )
        self.storage.upsert_event(first)
        self.storage.upsert_event(second)

        lookup = self.storage.get_known_updated_ms_map(["evt-1", "evt-2", "missing"])

        self.assertEqual(lookup, {"evt-1": 10, "evt-2": 20})

    def test_outbound_message_queue_dedupes_and_claims_ready_messages(self) -> None:
        first_insert = self.storage.enqueue_outbound_message(
            99,
            "hello",
            parse_mode="HTML",
            reply_markup={"keyboard": [[{"text": "Latest"}]]},
            category="alert",
            dedupe_key="alert:test:99:1",
        )
        duplicate_insert = self.storage.enqueue_outbound_message(
            99,
            "hello again",
            dedupe_key="alert:test:99:1",
        )

        self.assertTrue(first_insert)
        self.assertFalse(duplicate_insert)

        jobs = self.storage.claim_outbound_messages(limit=5, lease_seconds=45)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].chat_id, 99)
        self.assertEqual(jobs[0].parse_mode, "HTML")
        self.assertEqual(jobs[0].reply_markup, {"keyboard": [[{"text": "Latest"}]]})
        self.assertEqual(jobs[0].attempt_count, 1)

    def test_outbound_message_retry_and_sent_states_persist(self) -> None:
        inserted = self.storage.enqueue_outbound_message(
            123,
            "queued",
            dedupe_key="alert:test:123:1",
        )
        self.assertTrue(inserted)

        job = self.storage.claim_outbound_messages(limit=1, lease_seconds=30)[0]
        self.storage.retry_outbound_message(job.message_id, "temporary failure", 15)
        retried = self.storage.get_outbound_message(job.message_id)

        self.assertIsNotNone(retried)
        assert retried is not None
        self.assertEqual(retried.last_error, "temporary failure")
        self.assertIsNone(retried.sent_at)

        self.storage.mark_outbound_message_sent(job.message_id)
        sent = self.storage.get_outbound_message(job.message_id)

        self.assertIsNotNone(sent)
        assert sent is not None
        self.assertIsNotNone(sent.sent_at)
        self.assertIsNone(sent.last_error)

    def test_health_counts_reflect_events_subscriptions_and_queue(self) -> None:
        event = EarthquakeEvent(
            event_id="evt-health",
            updated_ms=30,
            magnitude=5.0,
            place="Health Check Place",
            event_time=datetime(2026, 3, 30, 11, 0, tzinfo=timezone.utc),
            detail_url="https://example.com/detail/health",
            event_url="https://example.com/event/health",
            latitude=7.0,
            longitude=8.0,
            depth_km=9.0,
            tsunami=False,
            status="reviewed",
            significance=300,
            felt_reports=3,
            alert_level=None,
            review_status="reviewed",
            shakemap_url=None,
            max_mmi=None,
        )
        self.storage.upsert_event(event)
        self.storage.upsert_subscription(99, 5.0, "Japan")
        self.storage.upsert_subscription(100, 5.5, None)
        self.storage.disable_subscription(100)
        self.storage.enqueue_outbound_message(99, "hello", category="alert", dedupe_key="health:test")

        queue_counts = self.storage.get_outbound_status_counts()

        self.assertEqual(self.storage.count_stored_events(), 1)
        self.assertEqual(self.storage.count_active_subscriptions(), 1)
        self.assertEqual(queue_counts.get("pending"), 1)

    def test_get_latest_matching_events_queries_full_history(self) -> None:
        matching = EarthquakeEvent(
            event_id="evt-japan-match",
            updated_ms=50,
            magnitude=4.4,
            place="81 km SE of Taira, Japan",
            event_time=datetime(2026, 3, 29, 1, 12, tzinfo=timezone.utc),
            detail_url="https://example.com/detail/japan",
            event_url="https://example.com/event/japan",
            latitude=36.1,
            longitude=141.2,
            depth_km=10.0,
            tsunami=False,
            status="reviewed",
            significance=400,
            felt_reports=12,
            alert_level=None,
            review_status="reviewed",
            shakemap_url=None,
            max_mmi=None,
        )
        self.storage.upsert_event(matching)
        for index in range(305):
            self.storage.upsert_event(
                EarthquakeEvent(
                    event_id=f"evt-nonmatch-{index}",
                    updated_ms=1000 + index,
                    magnitude=5.2,
                    place=f"{index} km SW of Anchorage, Alaska",
                    event_time=datetime(2026, 3, 30, 0, 0, tzinfo=timezone.utc).replace(minute=index % 60, second=index % 60),
                    detail_url=f"https://example.com/detail/nonmatch/{index}",
                    event_url=f"https://example.com/event/nonmatch/{index}",
                    latitude=61.1,
                    longitude=-150.1,
                    depth_km=10.0,
                    tsunami=False,
                    status="reviewed",
                    significance=300,
                    felt_reports=3,
                    alert_level=None,
                    review_status="reviewed",
                    shakemap_url=None,
                    max_mmi=None,
                )
            )

        rows = self.storage.get_latest_matching_events(0.0, ["Japan"], limit=5)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].event_id, "evt-japan-match")


if __name__ == "__main__":
    unittest.main()
