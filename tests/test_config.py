from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earthquake_bot.config import load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_defaults_to_polling_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            (base_dir / ".env").write_text("TELEGRAM_BOT_TOKEN=test-token\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                config = load_config(base_dir)

        self.assertEqual(config.telegram_mode, "polling")
        self.assertFalse(config.uses_webhook)
        self.assertIsNone(config.webhook_url)

    def test_load_config_derives_webhook_url_from_railway_domain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            (base_dir / ".env").write_text("TELEGRAM_BOT_TOKEN=test-token\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "TELEGRAM_MODE": "webhook",
                    "RAILWAY_PUBLIC_DOMAIN": "earthquake-monitor.up.railway.app",
                    "TELEGRAM_WEBHOOK_SECRET": "secret-123",
                },
                clear=True,
            ):
                config = load_config(base_dir)

        self.assertTrue(config.uses_webhook)
        self.assertEqual(config.webhook_url, "https://earthquake-monitor.up.railway.app/telegram/webhook")
        self.assertEqual(config.webhook_secret_token, "secret-123")


if __name__ == "__main__":
    unittest.main()
