from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earthquake_bot.telegram_api import TelegramApiError, TelegramClient


class TelegramApiTests(unittest.TestCase):
    def test_http_error_body_preserves_retry_after_and_description(self) -> None:
        client = TelegramClient("test-token")
        error = HTTPError(
            url="https://api.telegram.org/bottest/getUpdates",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=io.BytesIO(
                json.dumps(
                    {
                        "ok": False,
                        "error_code": 429,
                        "description": "Too Many Requests: retry after 7",
                        "parameters": {"retry_after": 7},
                    }
                ).encode("utf-8")
            ),
        )

        with patch("earthquake_bot.telegram_api.urlopen", side_effect=error):
            with self.assertRaises(TelegramApiError) as context:
                client.get_updates(timeout=1)

        self.assertEqual(context.exception.error_code, 429)
        self.assertEqual(context.exception.retry_after, 7)
        self.assertIn("retry after 7", context.exception.description or "")

    def test_parse_update_payload_supports_callback_queries(self) -> None:
        payload = {
            "update_id": 12,
            "callback_query": {
                "id": "cb-1",
                "data": "region|toggle|Asia|Japan",
                "from": {"first_name": "Darren"},
                "message": {
                    "message_id": 55,
                    "chat": {"id": 616580480},
                },
            },
        }

        update = TelegramClient.parse_update_payload(payload)

        self.assertIsNotNone(update)
        assert update is not None
        self.assertEqual(update.chat_id, 616580480)
        self.assertEqual(update.callback_query_id, "cb-1")
        self.assertEqual(update.callback_data, "region|toggle|Asia|Japan")

    def test_parse_update_payload_supports_messages(self) -> None:
        payload = {
            "update_id": 13,
            "message": {
                "message_id": 77,
                "text": "/help",
                "chat": {"id": 616580480},
                "from": {"first_name": "Darren"},
            },
        }

        update = TelegramClient.parse_update_payload(payload)

        self.assertIsNotNone(update)
        assert update is not None
        self.assertEqual(update.chat_id, 616580480)
        self.assertEqual(update.text, "/help")


if __name__ == "__main__":
    unittest.main()
