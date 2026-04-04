from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path

from earthquake_bot.config import load_config
from earthquake_bot.service import EarthquakeBotService
from earthquake_bot.storage import Storage
from earthquake_bot.telegram_api import TelegramApiError, TelegramClient
from earthquake_bot.usgs import USGSClient
from earthquake_bot.webhook_server import run_webhook_worker

OUTBOUND_BATCH_SIZE = 10
OUTBOUND_LEASE_SECONDS = 90
OUTBOUND_IDLE_SECONDS = 1.0
OUTBOUND_SEND_DELAY_SECONDS = 0.08
OUTBOUND_MAX_BACKOFF_SECONDS = 300


def configure_logging() -> None:
    log_dir = Path.cwd() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "bot.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
        force=True,
    )


def run_feed_worker(
    service: EarthquakeBotService,
    poll_seconds: int,
    stop_event: threading.Event,
) -> None:
    logger = logging.getLogger(__name__)
    while not stop_event.is_set():
        started_at = time.monotonic()
        try:
            changed_events = service.sync_earthquakes()
            logger.info("USGS sync complete. New or updated events: %s", changed_events)
        except Exception:
            logger.exception("Unexpected feed worker failure.")

        remaining = max(0.0, poll_seconds - (time.monotonic() - started_at))
        if stop_event.wait(remaining):
            return


def outbound_backoff_seconds(attempt_count: int, retry_after: int | None = None) -> int:
    if retry_after is not None:
        return max(1, retry_after + 1)
    exponent = max(0, attempt_count - 1)
    return min(OUTBOUND_MAX_BACKOFF_SECONDS, 5 * (2**exponent))


def is_permanent_telegram_error(error: TelegramApiError) -> bool:
    description = (error.description or str(error)).lower()
    if error.error_code in {400, 403}:
        permanent_markers = (
            "bot was blocked",
            "user is deactivated",
            "chat not found",
            "group chat was upgraded",
            "forbidden",
        )
        return any(marker in description for marker in permanent_markers)
    return False


def process_outbound_batch(
    storage: Storage,
    telegram_client: TelegramClient,
    stop_event: threading.Event,
    batch_size: int = OUTBOUND_BATCH_SIZE,
    lease_seconds: int = OUTBOUND_LEASE_SECONDS,
) -> int:
    logger = logging.getLogger(__name__)
    jobs = storage.claim_outbound_messages(limit=batch_size, lease_seconds=lease_seconds)
    if not jobs:
        return 0

    sent_count = 0
    for job in jobs:
        if stop_event.is_set():
            break
        try:
            if job.message_kind == "photo":
                if job.media is None:
                    raise ValueError("photo job is missing media bytes")
                telegram_client.send_photo(
                    job.chat_id,
                    job.media,
                    filename=job.media_filename or "alert-card.png",
                    caption=job.text or None,
                    parse_mode=job.parse_mode,
                    reply_markup=job.reply_markup,
                )
            else:
                telegram_client.send_message(
                    job.chat_id,
                    job.text,
                    parse_mode=job.parse_mode,
                    reply_markup=job.reply_markup,
                )
        except TelegramApiError as exc:
            if is_permanent_telegram_error(exc):
                storage.fail_outbound_message(job.message_id, str(exc))
                storage.disable_subscription(job.chat_id)
                logger.warning(
                    "Dropped outbound message %s for chat %s due to permanent Telegram error: %s",
                    job.message_id,
                    job.chat_id,
                    exc,
                )
                continue

            backoff = outbound_backoff_seconds(job.attempt_count, exc.retry_after)
            storage.retry_outbound_message(job.message_id, str(exc), backoff)
            logger.warning(
                "Retrying outbound message %s for chat %s in %ss after Telegram error: %s",
                job.message_id,
                job.chat_id,
                backoff,
                exc,
            )
            continue
        except Exception as exc:
            backoff = outbound_backoff_seconds(job.attempt_count)
            storage.retry_outbound_message(job.message_id, str(exc), backoff)
            logger.warning(
                "Retrying outbound message %s for chat %s in %ss after send failure: %s",
                job.message_id,
                job.chat_id,
                backoff,
                exc,
            )
            continue

        storage.mark_outbound_message_sent(job.message_id)
        sent_count += 1
        if stop_event.wait(OUTBOUND_SEND_DELAY_SECONDS):
            break

    return sent_count


def run_sender_worker(
    storage: Storage,
    telegram_client: TelegramClient,
    stop_event: threading.Event,
) -> None:
    logger = logging.getLogger(__name__)
    while not stop_event.is_set():
        try:
            sent_count = process_outbound_batch(storage, telegram_client, stop_event)
            if sent_count:
                logger.info("Outbound sender delivered %s queued message(s).", sent_count)
                continue
        except Exception:
            logger.exception("Unexpected sender worker failure.")

        if stop_event.wait(OUTBOUND_IDLE_SECONDS):
            return


def run_telegram_worker(
    storage: Storage,
    telegram_client: TelegramClient,
    service: EarthquakeBotService,
    long_poll_seconds: int,
    stop_event: threading.Event,
) -> None:
    logger = logging.getLogger(__name__)
    offset = int(storage.get_state("telegram_offset") or "0")

    while not stop_event.is_set():
        try:
            updates = telegram_client.get_updates(offset=offset, timeout=long_poll_seconds)
        except TelegramApiError:
            logger.exception("Telegram long poll failed.")
            if stop_event.wait(3):
                return
            continue
        except Exception:
            logger.exception("Unexpected telegram worker failure.")
            if stop_event.wait(3):
                return
            continue

        pending_offset = offset
        for update in updates:
            if stop_event.is_set():
                return
            pending_offset = max(pending_offset, update.update_id + 1)
            try:
                service.handle_update(update)
            except Exception:
                logger.exception("Failed to process update %s.", update.update_id)

        if pending_offset != offset:
            try:
                storage.set_state("telegram_offset", str(pending_offset))
                offset = pending_offset
            except Exception:
                logger.exception("Failed to persist Telegram offset %s.", pending_offset)
                if stop_event.wait(1):
                    return


def start_worker(
    name: str,
    target,
    *args,
) -> threading.Thread:
    thread = threading.Thread(name=name, target=target, args=args, daemon=True)
    thread.start()
    return thread


def main() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)

    config = load_config(Path.cwd())
    storage = Storage(config.database_path)
    usgs_client = USGSClient(config.usgs_feed_url)
    telegram_client = TelegramClient(config.telegram_bot_token)
    service = EarthquakeBotService(config, storage, usgs_client, telegram_client)

    logger.info(
        "Earthquake bot started. Transport=%s. Polling USGS feed every %s seconds.",
        config.telegram_mode,
        config.usgs_poll_seconds,
    )
    try:
        if config.uses_webhook:
            webhook_url = config.webhook_url
            assert webhook_url is not None
            telegram_client.set_webhook(webhook_url, secret_token=config.webhook_secret_token)
            logger.info("Telegram webhook configured at %s", webhook_url)
        else:
            telegram_client.delete_webhook(drop_pending_updates=False)
            logger.info("Telegram webhook cleared. Using long polling.")
    except TelegramApiError:
        logger.exception("Failed to configure Telegram transport.")

    try:
        telegram_client.clear_my_commands()
        logger.info("Telegram slash command menu cleared. Reply keyboard remains available.")
    except TelegramApiError:
        logger.exception("Failed to clear Telegram bot commands.")

    stop_event = threading.Event()
    workers: dict[str, tuple[object, tuple[object, ...], threading.Thread]] = {
        "feed": (
            run_feed_worker,
            (service, config.usgs_poll_seconds, stop_event),
            start_worker(
                "feed-worker",
                run_feed_worker,
                service,
                config.usgs_poll_seconds,
                stop_event,
            ),
        ),
        "sender": (
            run_sender_worker,
            (storage, telegram_client, stop_event),
            start_worker(
                "sender-worker",
                run_sender_worker,
                storage,
                telegram_client,
                stop_event,
            ),
        ),
    }
    if config.uses_webhook:
        workers["telegram-webhook"] = (
            run_webhook_worker,
            (service, config, stop_event),
            start_worker(
                "telegram-webhook-worker",
                run_webhook_worker,
                service,
                config,
                stop_event,
            ),
        )
    else:
        workers["telegram-polling"] = (
            run_telegram_worker,
            (storage, telegram_client, service, config.telegram_long_poll_seconds, stop_event),
            start_worker(
                "telegram-polling-worker",
                run_telegram_worker,
                storage,
                telegram_client,
                service,
                config.telegram_long_poll_seconds,
                stop_event,
            ),
        )

    while True:
        try:
            time.sleep(1)
            for name, (target, args, thread) in list(workers.items()):
                if thread.is_alive():
                    continue
                logger.error("%s stopped unexpectedly. Restarting worker.", thread.name)
                workers[name] = (target, args, start_worker(f"{name}-worker", target, *args))
        except KeyboardInterrupt:
            logger.info("Shutdown requested. Stopping workers.")
            stop_event.set()
            break
        except Exception:
            logger.exception("Unexpected supervisor failure. The bot will keep running.")
            time.sleep(3)

    for _, _, thread in workers.values():
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
