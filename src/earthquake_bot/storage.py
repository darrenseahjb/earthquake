from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from earthquake_bot.models import EarthquakeEvent, OutboundMessage, Subscription


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS bot_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS subscriptions (
                    chat_id INTEGER PRIMARY KEY,
                    min_magnitude REAL NOT NULL,
                    region_filter TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS earthquake_events (
                    event_id TEXT PRIMARY KEY,
                    updated_ms INTEGER NOT NULL,
                    magnitude REAL,
                    place TEXT NOT NULL,
                    event_time TEXT NOT NULL,
                    detail_url TEXT NOT NULL,
                    event_url TEXT NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    depth_km REAL,
                    tsunami INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    significance INTEGER,
                    felt_reports INTEGER,
                    alert_level TEXT,
                    review_status TEXT,
                    shakemap_url TEXT,
                    max_mmi REAL,
                    last_synced_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_earthquake_events_event_time
                ON earthquake_events (event_time DESC);

                CREATE INDEX IF NOT EXISTS idx_subscriptions_enabled
                ON subscriptions (enabled);

                CREATE TABLE IF NOT EXISTS outbound_messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    message_kind TEXT NOT NULL DEFAULT 'text',
                    text TEXT NOT NULL,
                    parse_mode TEXT,
                    reply_markup TEXT,
                    media BLOB,
                    media_filename TEXT,
                    category TEXT NOT NULL,
                    dedupe_key TEXT UNIQUE,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT NOT NULL,
                    leased_until TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    sent_at TEXT,
                    last_error TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_outbound_messages_ready
                ON outbound_messages (status, next_attempt_at, message_id);

                CREATE INDEX IF NOT EXISTS idx_outbound_messages_lease
                ON outbound_messages (leased_until);
                """
            )
            self._ensure_outbound_message_columns(connection)

    def _ensure_outbound_message_columns(self, connection: sqlite3.Connection) -> None:
        columns = {
            "message_kind": "TEXT NOT NULL DEFAULT 'text'",
            "media": "BLOB",
            "media_filename": "TEXT",
        }
        existing = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(outbound_messages)").fetchall()
        }
        for column, definition in columns.items():
            if column not in existing:
                connection.execute(f"ALTER TABLE outbound_messages ADD COLUMN {column} {definition}")

    def get_state(self, key: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute("SELECT value FROM bot_state WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def set_state(self, key: str, value: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO bot_state (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def delete_state(self, key: str) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM bot_state WHERE key = ?", (key,))

    def get_chat_context(self, chat_id: int) -> dict[str, Any] | None:
        raw = self.get_state(self._chat_context_key(chat_id))
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def set_chat_context(self, chat_id: int, step: str, value: Any | None = None) -> None:
        self.set_state(
            self._chat_context_key(chat_id),
            json.dumps({"step": step, "value": value}, separators=(",", ":")),
        )

    def clear_chat_context(self, chat_id: int) -> None:
        self.delete_state(self._chat_context_key(chat_id))

    def get_chat_timezone(self, chat_id: int) -> str | None:
        return self.get_state(self._chat_timezone_key(chat_id))

    def set_chat_timezone(self, chat_id: int, timezone_name: str) -> None:
        self.set_state(self._chat_timezone_key(chat_id), timezone_name)

    def get_known_updated_ms_map(self, event_ids: list[str]) -> dict[str, int]:
        if not event_ids:
            return {}

        placeholders = ",".join("?" for _ in event_ids)
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT event_id, updated_ms
                FROM earthquake_events
                WHERE event_id IN ({placeholders})
                """,
                event_ids,
            ).fetchall()
        return {str(row["event_id"]): int(row["updated_ms"]) for row in rows}

    def upsert_event(self, event: EarthquakeEvent) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO earthquake_events (
                    event_id,
                    updated_ms,
                    magnitude,
                    place,
                    event_time,
                    detail_url,
                    event_url,
                    latitude,
                    longitude,
                    depth_km,
                    tsunami,
                    status,
                    significance,
                    felt_reports,
                    alert_level,
                    review_status,
                    shakemap_url,
                    max_mmi,
                    last_synced_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    updated_ms = excluded.updated_ms,
                    magnitude = excluded.magnitude,
                    place = excluded.place,
                    event_time = excluded.event_time,
                    detail_url = excluded.detail_url,
                    event_url = excluded.event_url,
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    depth_km = excluded.depth_km,
                    tsunami = excluded.tsunami,
                    status = excluded.status,
                    significance = excluded.significance,
                    felt_reports = excluded.felt_reports,
                    alert_level = excluded.alert_level,
                    review_status = excluded.review_status,
                    shakemap_url = excluded.shakemap_url,
                    max_mmi = excluded.max_mmi,
                    last_synced_at = excluded.last_synced_at
                """,
                (
                    event.event_id,
                    event.updated_ms,
                    event.magnitude,
                    event.place,
                    event.event_time.isoformat(),
                    event.detail_url,
                    event.event_url,
                    event.latitude,
                    event.longitude,
                    event.depth_km,
                    1 if event.tsunami else 0,
                    event.status,
                    event.significance,
                    event.felt_reports,
                    event.alert_level,
                    event.review_status,
                    event.shakemap_url,
                    event.max_mmi,
                    utc_now_iso(),
                ),
            )

    def enqueue_outbound_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        category: str = "alert",
        dedupe_key: str | None = None,
        message_kind: str = "text",
        media: bytes | None = None,
        media_filename: str | None = None,
    ) -> bool:
        timestamp = utc_now_iso()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO outbound_messages (
                    chat_id,
                    message_kind,
                    text,
                    parse_mode,
                    reply_markup,
                    media,
                    media_filename,
                    category,
                    dedupe_key,
                    status,
                    attempt_count,
                    next_attempt_at,
                    leased_until,
                    created_at,
                    updated_at,
                    sent_at,
                    last_error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, NULL, ?, ?, NULL, NULL)
                ON CONFLICT(dedupe_key) DO NOTHING
                """,
                (
                    chat_id,
                    message_kind,
                    text,
                    parse_mode,
                    json.dumps(reply_markup, separators=(",", ":")) if reply_markup is not None else None,
                    sqlite3.Binary(media) if media is not None else None,
                    media_filename,
                    category,
                    dedupe_key,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
        return cursor.rowcount > 0

    def claim_outbound_messages(self, limit: int = 20, lease_seconds: int = 60) -> list[OutboundMessage]:
        if limit <= 0:
            return []

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        lease_until_iso = (now + timedelta(seconds=max(1, lease_seconds))).isoformat()

        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT message_id
                FROM outbound_messages
                WHERE status IN ('pending', 'retry')
                  AND next_attempt_at <= ?
                  AND (leased_until IS NULL OR leased_until <= ?)
                ORDER BY next_attempt_at ASC, message_id ASC
                LIMIT ?
                """,
                (now_iso, now_iso, limit),
            ).fetchall()

            message_ids = [int(row["message_id"]) for row in rows]
            if not message_ids:
                return []

            placeholders = ",".join("?" for _ in message_ids)
            connection.execute(
                f"""
                UPDATE outbound_messages
                SET status = 'sending',
                    leased_until = ?,
                    attempt_count = attempt_count + 1,
                    updated_at = ?
                WHERE message_id IN ({placeholders})
                """,
                (lease_until_iso, now_iso, *message_ids),
            )
            claimed_rows = connection.execute(
                f"""
                SELECT *
                FROM outbound_messages
                WHERE message_id IN ({placeholders})
                ORDER BY next_attempt_at ASC, message_id ASC
                """,
                message_ids,
            ).fetchall()
        return [self._row_to_outbound_message(row) for row in claimed_rows]

    def mark_outbound_message_sent(self, message_id: int) -> None:
        timestamp = utc_now_iso()
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE outbound_messages
                SET status = 'sent',
                    leased_until = NULL,
                    sent_at = ?,
                    updated_at = ?,
                    last_error = NULL
                WHERE message_id = ?
                """,
                (timestamp, timestamp, message_id),
            )

    def retry_outbound_message(self, message_id: int, error: str, delay_seconds: int) -> None:
        delay = max(1, delay_seconds)
        now = datetime.now(timezone.utc)
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE outbound_messages
                SET status = 'retry',
                    leased_until = NULL,
                    next_attempt_at = ?,
                    updated_at = ?,
                    last_error = ?
                WHERE message_id = ?
                """,
                ((now + timedelta(seconds=delay)).isoformat(), now.isoformat(), error[:1000], message_id),
            )

    def fail_outbound_message(self, message_id: int, error: str) -> None:
        timestamp = utc_now_iso()
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE outbound_messages
                SET status = 'failed',
                    leased_until = NULL,
                    updated_at = ?,
                    last_error = ?
                WHERE message_id = ?
                """,
                (timestamp, error[:1000], message_id),
            )

    def get_outbound_message(self, message_id: int) -> OutboundMessage | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM outbound_messages WHERE message_id = ?",
                (message_id,),
            ).fetchone()
        return None if row is None else self._row_to_outbound_message(row)

    def get_outbound_status_counts(self) -> dict[str, int]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM outbound_messages
                GROUP BY status
                """
            ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}

    def count_stored_events(self) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM earthquake_events").fetchone()
        return 0 if row is None else int(row["count"])

    def count_active_subscriptions(self) -> int:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM subscriptions WHERE enabled = 1"
            ).fetchone()
        return 0 if row is None else int(row["count"])

    def get_latest_events(self, limit: int = 5) -> list[EarthquakeEvent]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM earthquake_events
                ORDER BY event_time DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def get_latest_matching_events(
        self,
        min_magnitude: float,
        region_filters: list[str] | None = None,
        limit: int = 5,
    ) -> list[EarthquakeEvent]:
        where_clauses = ["COALESCE(magnitude, 0) >= ?"]
        params: list[Any] = [min_magnitude]

        cleaned_filters = [region.strip().lower() for region in (region_filters or []) if region.strip()]
        if cleaned_filters:
            like_clauses = []
            for region in cleaned_filters:
                like_clauses.append("LOWER(place) LIKE ?")
                params.append(f"%{region}%")
            where_clauses.append(f"({' OR '.join(like_clauses)})")

        params.append(limit)
        query = f"""
            SELECT *
            FROM earthquake_events
            WHERE {' AND '.join(where_clauses)}
            ORDER BY event_time DESC
            LIMIT ?
        """

        with self._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_event(row) for row in rows]

    def upsert_subscription(self, chat_id: int, min_magnitude: float, region_filter: str | None) -> None:
        timestamp = utc_now_iso()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO subscriptions (
                    chat_id,
                    min_magnitude,
                    region_filter,
                    enabled,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    min_magnitude = excluded.min_magnitude,
                    region_filter = excluded.region_filter,
                    enabled = 1,
                    updated_at = excluded.updated_at
                """,
                (chat_id, min_magnitude, region_filter, timestamp, timestamp),
            )

    def disable_subscription(self, chat_id: int) -> bool:
        with self._connection() as connection:
            result = connection.execute(
                """
                UPDATE subscriptions
                SET enabled = 0, updated_at = ?
                WHERE chat_id = ? AND enabled = 1
                """,
                (utc_now_iso(), chat_id),
            )
        return result.rowcount > 0

    def get_subscription(self, chat_id: int) -> Subscription | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM subscriptions WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        return None if row is None else self._row_to_subscription(row)

    def list_active_subscriptions(self) -> list[Subscription]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM subscriptions WHERE enabled = 1"
            ).fetchall()
        return [self._row_to_subscription(row) for row in rows]

    def get_event(self, event_id: str) -> EarthquakeEvent | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM earthquake_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return None if row is None else self._row_to_event(row)

    def _row_to_event(self, row: sqlite3.Row) -> EarthquakeEvent:
        return EarthquakeEvent(
            event_id=str(row["event_id"]),
            updated_ms=int(row["updated_ms"]),
            magnitude=row["magnitude"],
            place=str(row["place"]),
            event_time=datetime.fromisoformat(str(row["event_time"])),
            detail_url=str(row["detail_url"]),
            event_url=str(row["event_url"]),
            latitude=row["latitude"],
            longitude=row["longitude"],
            depth_km=row["depth_km"],
            tsunami=bool(row["tsunami"]),
            status=str(row["status"]),
            significance=row["significance"],
            felt_reports=row["felt_reports"],
            alert_level=row["alert_level"],
            review_status=row["review_status"],
            shakemap_url=row["shakemap_url"],
            max_mmi=row["max_mmi"],
        )

    def _row_to_subscription(self, row: sqlite3.Row) -> Subscription:
        return Subscription(
            chat_id=int(row["chat_id"]),
            min_magnitude=float(row["min_magnitude"]),
            region_filter=row["region_filter"],
            enabled=bool(row["enabled"]),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
        )

    def _row_to_outbound_message(self, row: sqlite3.Row) -> OutboundMessage:
        reply_markup = row["reply_markup"]
        parsed_markup: dict[str, Any] | None = None
        if reply_markup:
            try:
                parsed = json.loads(str(reply_markup))
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                parsed_markup = parsed

        leased_until = row["leased_until"]
        sent_at = row["sent_at"]
        last_error = row["last_error"]
        return OutboundMessage(
            message_id=int(row["message_id"]),
            chat_id=int(row["chat_id"]),
            message_kind=str(row["message_kind"] or "text"),
            text=str(row["text"]),
            parse_mode=row["parse_mode"],
            reply_markup=parsed_markup,
            media=None if row["media"] is None else bytes(row["media"]),
            media_filename=row["media_filename"],
            category=str(row["category"]),
            dedupe_key=row["dedupe_key"],
            attempt_count=int(row["attempt_count"]),
            next_attempt_at=datetime.fromisoformat(str(row["next_attempt_at"])),
            leased_until=datetime.fromisoformat(str(leased_until)) if leased_until else None,
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
            sent_at=datetime.fromisoformat(str(sent_at)) if sent_at else None,
            last_error=None if last_error is None else str(last_error),
        )

    def _chat_context_key(self, chat_id: int) -> str:
        return f"chat_context:{chat_id}"

    def _chat_timezone_key(self, chat_id: int) -> str:
        return f"chat_timezone:{chat_id}"
