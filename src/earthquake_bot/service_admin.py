from __future__ import annotations

import html
from datetime import datetime, timezone

from earthquake_bot.models import EarthquakeEvent
from earthquake_bot.service_constants import ADMIN_BROADCAST_USAGE, ADMIN_HEALTH_LABEL, ADMIN_TEST_LABEL


class ServiceAdminMixin:
    def _is_admin(self, chat_id: int) -> bool:
        return chat_id in self.config.admin_chat_ids

    def _status_reply_markup(self, chat_id: int) -> dict[str, object]:
        if self._is_admin(chat_id):
            return self._admin_status_keyboard()
        return self._quick_actions_keyboard()

    def _admin_status_keyboard(self) -> dict[str, object]:
        return {
            "inline_keyboard": [
                [
                    self._inline_button(ADMIN_TEST_LABEL, self._admin_callback("test")),
                    self._inline_button(ADMIN_HEALTH_LABEL, self._admin_callback("health")),
                ]
            ]
        }

    def _health_text(self, chat_id: int) -> str:
        queue_counts = self.storage.get_outbound_status_counts()
        waiting_count = (
            queue_counts.get("pending", 0)
            + queue_counts.get("retry", 0)
            + queue_counts.get("sending", 0)
        )
        rows = [
            ("role", "admin"),
            ("mode", self.config.telegram_mode),
            ("subs", f"{self.storage.count_active_subscriptions()} active"),
            ("stored", f"{self.storage.count_stored_events()} quakes"),
            ("queue", f"{waiting_count} waiting"),
            ("failed", str(queue_counts.get("failed", 0))),
            ("sent", str(queue_counts.get("sent", 0))),
            ("offset", self.storage.get_state("telegram_offset") or "-"),
            ("feed", f"{self.storage.get_state('last_feed_event_count') or '0'} events"),
            ("sync", self._format_state_time(chat_id, self.storage.get_state("last_feed_sync_at") or "never")),
            ("poll", f"{self.config.usgs_poll_seconds}s"),
        ]
        return f"<b>Health Snapshot</b>\n{self._format_rows(rows)}"

    def _queue_admin_test_alert(self, chat_id: int) -> bool:
        event_time = datetime.now(timezone.utc)
        updated_ms = int(event_time.timestamp() * 1000)
        event = EarthquakeEvent(
            event_id=f"admin-test-{updated_ms}",
            updated_ms=updated_ms,
            magnitude=5.1,
            place="TEST ONLY - 81 km SE of Taira, Japan",
            event_time=event_time,
            detail_url="https://earthquake.usgs.gov/earthquakes/feed/",
            event_url="https://earthquake.usgs.gov/earthquakes/eventpage/us7000s8mj",
            latitude=36.1,
            longitude=141.2,
            depth_km=10.0,
            tsunami=False,
            status="reviewed",
            significance=400,
            felt_reports=None,
            alert_level=None,
            review_status="automatic",
            shakemap_url=None,
            max_mmi=None,
        )
        return self._enqueue_event_alert(
            chat_id,
            event,
            is_update=False,
            dedupe_key=f"admin-test:{chat_id}:{updated_ms}",
            title_override="Demo Alert",
            advisories_override=[
                "Admin preview only. Not a real earthquake notification.",
                "No action needed.",
            ],
            source_caption_override="<b>Demo only.</b> Sent from admin test tools.",
        )

    def _broadcast_admin_message(self, raw_text: str) -> str:
        message = raw_text.strip()
        if not message:
            return f"<b>Broadcast Skipped</b>\nUsage: <code>{ADMIN_BROADCAST_USAGE}</code>"

        subscriptions = self.storage.list_active_subscriptions()
        chat_ids = sorted({subscription.chat_id for subscription in subscriptions if subscription.enabled})
        queued_count = 0
        for chat_id in chat_ids:
            queued = self.storage.enqueue_outbound_message(
                chat_id,
                f"<b>Earthquake Monitor Broadcast</b>\n{html.escape(message)}",
                parse_mode="HTML",
                reply_markup=self._quick_actions_keyboard(),
                category="admin_broadcast",
            )
            if queued:
                queued_count += 1

        return (
            "<b>Broadcast Queued</b>\n"
            f"Queued for <code>{queued_count}</code> active subscriber chats."
        )

    def _handle_admin_callback(self, update) -> bool:
        callback_data = update.callback_data or ""
        if not callback_data.startswith("admin|"):
            return False

        if not self._is_admin(update.chat_id):
            self._answer_callback(update, "Admin only.")
            return True

        action = self._parse_admin_callback(callback_data)
        if action == "test":
            queued = self._queue_admin_test_alert(update.chat_id)
            self._answer_callback(update, "Queued." if queued else "Skipped.")
            self.telegram_client.send_message(
                update.chat_id,
                "<b>Demo Alert Queued</b>\nA clearly marked admin-only preview is on the way."
                if queued
                else "<b>Demo Alert Skipped</b>\nThe preview alert could not be queued.",
                parse_mode="HTML",
                reply_markup=self._quick_actions_keyboard(),
            )
            return True

        if action == "health":
            self._answer_callback(update, "Health sent.")
            self.telegram_client.send_message(
                update.chat_id,
                self._health_text(update.chat_id),
                parse_mode="HTML",
                reply_markup=self._quick_actions_keyboard(),
            )
            return True

        self._answer_callback(update)
        return True

    def _admin_callback(self, action: str) -> str:
        return f"admin|{action}"

    def _parse_admin_callback(self, payload: str) -> str:
        parts = payload.split("|", 1)
        return parts[1] if len(parts) == 2 else ""
