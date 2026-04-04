from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earthquake_bot.main import process_outbound_batch, run_telegram_worker
from earthquake_bot.storage import Storage
from earthquake_bot.telegram_api import TelegramApiError, TelegramUpdate


class StubTelegramClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.sent_messages: list[dict[str, object]] = []
        self.sent_photos: list[dict[str, object]] = []

    def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, object] | None = None,
    ) -> None:
        if self.error is not None:
            raise self.error
        self.sent_messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
            }
        )

    def send_photo(
        self,
        chat_id: int,
        photo_bytes: bytes,
        filename: str = "alert-card.png",
        caption: str | None = None,
        parse_mode: str | None = None,
        reply_markup: dict[str, object] | None = None,
    ) -> None:
        if self.error is not None:
            raise self.error
        self.sent_photos.append(
            {
                "chat_id": chat_id,
                "photo_bytes": photo_bytes,
                "filename": filename,
                "caption": caption,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
            }
        )


class MainQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.temp_dir.name) / "bot.sqlite3")
        self.stop_event = threading.Event()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_process_outbound_batch_sends_and_marks_sent(self) -> None:
        self.storage.enqueue_outbound_message(
            99,
            "queued alert",
            parse_mode="HTML",
            reply_markup={"keyboard": [[{"text": "Latest"}]]},
            dedupe_key="alert:99:1",
        )
        client = StubTelegramClient()

        sent_count = process_outbound_batch(self.storage, client, self.stop_event, batch_size=5, lease_seconds=30)

        self.assertEqual(sent_count, 1)
        self.assertEqual(len(client.sent_messages), 1)
        job = self.storage.get_outbound_message(1)
        self.assertIsNotNone(job)
        assert job is not None
        self.assertIsNotNone(job.sent_at)
        self.assertIsNone(job.last_error)

    def test_process_outbound_batch_retries_rate_limited_messages(self) -> None:
        self.storage.enqueue_outbound_message(
            77,
            "queued alert",
            dedupe_key="alert:77:1",
        )
        client = StubTelegramClient(
            TelegramApiError(
                "rate limited",
                error_code=429,
                description="Too Many Requests: retry after 7",
                retry_after=7,
            )
        )

        sent_count = process_outbound_batch(self.storage, client, self.stop_event, batch_size=5, lease_seconds=30)

        self.assertEqual(sent_count, 0)
        job = self.storage.get_outbound_message(1)
        self.assertIsNotNone(job)
        assert job is not None
        self.assertIsNone(job.sent_at)
        self.assertEqual(job.attempt_count, 1)
        self.assertIsNotNone(job.last_error)
        self.assertEqual(self.storage.claim_outbound_messages(limit=1, lease_seconds=30), [])

    def test_process_outbound_batch_fails_permanent_errors_and_disables_subscription(self) -> None:
        self.storage.upsert_subscription(88, 5.0, None)
        self.storage.enqueue_outbound_message(
            88,
            "queued alert",
            dedupe_key="alert:88:1",
        )
        client = StubTelegramClient(
            TelegramApiError(
                "blocked",
                error_code=403,
                description="Forbidden: bot was blocked by the user",
            )
        )

        sent_count = process_outbound_batch(self.storage, client, self.stop_event, batch_size=5, lease_seconds=30)

        self.assertEqual(sent_count, 0)
        job = self.storage.get_outbound_message(1)
        self.assertIsNotNone(job)
        assert job is not None
        self.assertIsNone(job.sent_at)
        self.assertIsNotNone(job.last_error)
        subscription = self.storage.get_subscription(88)
        self.assertIsNotNone(subscription)
        assert subscription is not None
        self.assertFalse(subscription.enabled)

    def test_process_outbound_batch_sends_photo_jobs(self) -> None:
        self.storage.enqueue_outbound_message(
            55,
            "<b>Official source:</b> <a href=\"https://example.com\">USGS</a>",
            parse_mode="HTML",
            message_kind="photo",
            media=b"fakepng",
            media_filename="card.png",
            dedupe_key="alert:55:photo",
        )
        client = StubTelegramClient()

        sent_count = process_outbound_batch(self.storage, client, self.stop_event, batch_size=5, lease_seconds=30)

        self.assertEqual(sent_count, 1)
        self.assertEqual(len(client.sent_photos), 1)
        self.assertEqual(client.sent_photos[0]["filename"], "card.png")
        job = self.storage.get_outbound_message(1)
        self.assertIsNotNone(job)
        assert job is not None
        self.assertIsNotNone(job.sent_at)

    def test_run_telegram_worker_persists_offset_after_processing_batch(self) -> None:
        stop_event = threading.Event()

        class StubStorage:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str, str]] = []

            def get_state(self, key: str) -> str | None:
                self.calls.append(("get_state", key, ""))
                return "0"

            def set_state(self, key: str, value: str) -> None:
                self.calls.append(("set_state", key, value))

        class StubTelegramUpdatesClient:
            def __init__(self) -> None:
                self.call_count = 0

            def get_updates(self, offset: int | None = None, timeout: int = 25) -> list[TelegramUpdate]:
                self.call_count += 1
                if self.call_count == 1:
                    return [
                        TelegramUpdate(1, 99, "/help", "Darren"),
                        TelegramUpdate(2, 99, "/status", "Darren"),
                    ]
                stop_event.set()
                return []

        class StubService:
            def __init__(self, storage: StubStorage) -> None:
                self.storage = storage
                self.handled: list[tuple[int, int]] = []

            def handle_update(self, update: TelegramUpdate) -> None:
                set_state_calls = [call for call in self.storage.calls if call[0] == "set_state"]
                self.handled.append((update.update_id, len(set_state_calls)))

        storage = StubStorage()
        telegram_client = StubTelegramUpdatesClient()
        service = StubService(storage)

        run_telegram_worker(storage, telegram_client, service, 1, stop_event)

        self.assertEqual(service.handled, [(1, 0), (2, 0)])
        self.assertIn(("set_state", "telegram_offset", "3"), storage.calls)


if __name__ == "__main__":
    unittest.main()
