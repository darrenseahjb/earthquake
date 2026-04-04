from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_FEED_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"


@dataclass(slots=True)
class Config:
    telegram_bot_token: str
    usgs_feed_url: str
    usgs_poll_seconds: int
    default_min_magnitude: float
    database_path: Path
    telegram_long_poll_seconds: int
    admin_chat_ids: frozenset[int] = frozenset()
    telegram_mode: str = "polling"
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080
    webhook_path: str = "/telegram/webhook"
    webhook_base_url: str | None = None
    webhook_secret_token: str | None = None

    @property
    def uses_webhook(self) -> bool:
        return self.telegram_mode == "webhook"

    @property
    def webhook_url(self) -> str | None:
        if not self.webhook_base_url:
            return None
        return f"{self.webhook_base_url.rstrip('/')}{self.webhook_path}"


def load_dotenv(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def parse_admin_chat_ids(raw_value: str) -> frozenset[int]:
    admin_chat_ids: set[int] = set()
    for part in raw_value.split(","):
        stripped = part.strip()
        if not stripped:
            continue
        try:
            admin_chat_ids.add(int(stripped))
        except ValueError:
            continue
    return frozenset(admin_chat_ids)


def load_config(base_dir: Path | None = None) -> Config:
    resolved_base = base_dir or Path.cwd()
    load_dotenv(resolved_base / ".env")

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required. Add it to your environment or .env file.")

    feed_url = os.getenv("USGS_FEED_URL", DEFAULT_FEED_URL).strip() or DEFAULT_FEED_URL
    poll_seconds = max(60, int(os.getenv("USGS_POLL_SECONDS", "60")))
    default_min_magnitude = float(os.getenv("DEFAULT_MIN_MAGNITUDE", "5.0"))
    database_path = Path(os.getenv("DATABASE_PATH", "data/earthquake_bot.sqlite3"))
    long_poll_seconds = max(1, min(50, int(os.getenv("TELEGRAM_LONG_POLL_SECONDS", "25"))))
    admin_chat_ids = parse_admin_chat_ids(os.getenv("ADMIN_CHAT_IDS", ""))
    telegram_mode = (os.getenv("TELEGRAM_MODE", "polling").strip().lower() or "polling")
    if telegram_mode not in {"polling", "webhook"}:
        raise ValueError("TELEGRAM_MODE must be either 'polling' or 'webhook'.")

    webhook_host = os.getenv("WEBHOOK_HOST", "0.0.0.0").strip() or "0.0.0.0"
    webhook_port = max(1, int(os.getenv("PORT", os.getenv("WEBHOOK_PORT", "8080"))))
    webhook_path = os.getenv("WEBHOOK_PATH", "/telegram/webhook").strip() or "/telegram/webhook"
    if not webhook_path.startswith("/"):
        webhook_path = f"/{webhook_path}"

    webhook_base_url = os.getenv("WEBHOOK_BASE_URL", "").strip()
    if not webhook_base_url:
        railway_public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
        if railway_public_domain:
            webhook_base_url = f"https://{railway_public_domain}"
    webhook_base_url = webhook_base_url or None

    webhook_secret_token = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip() or None

    if not database_path.is_absolute():
        database_path = resolved_base / database_path

    if telegram_mode == "webhook" and webhook_base_url is None:
        raise ValueError(
            "WEBHOOK_BASE_URL is required when TELEGRAM_MODE=webhook unless RAILWAY_PUBLIC_DOMAIN is set."
        )

    return Config(
        telegram_bot_token=token,
        usgs_feed_url=feed_url,
        usgs_poll_seconds=poll_seconds,
        default_min_magnitude=default_min_magnitude,
        database_path=database_path,
        telegram_long_poll_seconds=long_poll_seconds,
        admin_chat_ids=admin_chat_ids,
        telegram_mode=telegram_mode,
        webhook_host=webhook_host,
        webhook_port=webhook_port,
        webhook_path=webhook_path,
        webhook_base_url=webhook_base_url,
        webhook_secret_token=webhook_secret_token,
    )
