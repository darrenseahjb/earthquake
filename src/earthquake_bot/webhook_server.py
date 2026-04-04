from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from earthquake_bot.telegram_api import TelegramClient

if TYPE_CHECKING:
    import threading

    from earthquake_bot.config import Config
    from earthquake_bot.service import EarthquakeBotService


logger = logging.getLogger(__name__)


class TelegramWebhookServer(HTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        service: EarthquakeBotService,
        config: Config,
    ) -> None:
        super().__init__(server_address, TelegramWebhookHandler)
        self.bot_service = service
        self.webhook_path = config.webhook_path
        self.secret_token = config.webhook_secret_token
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="telegram-update")

    def close(self) -> None:
        self.server_close()
        self.executor.shutdown(wait=False, cancel_futures=False)


class TelegramWebhookHandler(BaseHTTPRequestHandler):
    server: TelegramWebhookServer

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path in {"", "/", "/healthz"}:
            self._write_json(200, {"ok": True, "status": "healthy"})
            return
        self._write_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path != self.server.webhook_path:
            self._write_json(404, {"ok": False, "error": "not_found"})
            return

        if self.server.secret_token:
            provided_secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if provided_secret != self.server.secret_token:
                self._write_json(403, {"ok": False, "error": "forbidden"})
                return

        content_length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(max(0, content_length))

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._write_json(400, {"ok": False, "error": "invalid_json"})
            return

        update = TelegramClient.parse_update_payload(payload)
        if update is not None:
            self.server.executor.submit(self._safe_process_update, update)

        self._write_json(200, {"ok": True})

    def log_message(self, format: str, *args: object) -> None:
        logger.debug("Webhook HTTP: " + format, *args)

    def _write_json(self, status_code: int, payload: dict[str, object]) -> None:
        response = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def _safe_process_update(self, update) -> None:
        try:
            self.server.bot_service.handle_update(update)
        except Exception:
            logger.exception("Failed to process webhook update %s.", update.update_id)


def run_webhook_worker(
    service: EarthquakeBotService,
    config: Config,
    stop_event: threading.Event,
) -> None:
    server = TelegramWebhookServer((config.webhook_host, config.webhook_port), service, config)
    server.timeout = 0.5
    logger.info(
        "Webhook server listening on %s:%s%s",
        config.webhook_host,
        config.webhook_port,
        config.webhook_path,
    )
    try:
        while not stop_event.is_set():
            server.handle_request()
    finally:
        server.close()
