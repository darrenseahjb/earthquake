from __future__ import annotations

import html
from datetime import datetime

from earthquake_bot.service_constants import (
    LATEST_LABEL,
    LATEST_SUBSCRIBED_LABEL,
    REGION_FLAGS,
    SUBSCRIBE_ALL_OPTION_LABEL,
    SUBSCRIBE_LABEL,
    SUBSCRIBE_REGION_OPTION_LABEL,
)


class ServiceTextMixin:
    def _start_text(self) -> str:
        return (
            "<b>Earthquake Monitor</b>\n"
            "Live USGS quake alerts with clean filters.\n"
            "\n"
            "Use the button menu below to get started."
        )

    def _help_text(self) -> str:
        return (
            "<b>Menu</b>\n"
            "<b>Subscribe</b> - choose global alerts or pick countries\n"
            "<b>Latest subscribed</b> - recent quakes for your selected regions\n"
            f"<b>{LATEST_LABEL}</b> - recent stored quakes across the full feed\n"
            "<b>Status</b> - current filters and sync info\n"
            "<b>Unsubscribe</b> - pause alerts\n"
            "<b>Edit Timezone</b> - change your local quake time\n"
            "\n"
            "If the buttons disappear, send <code>/help</code>."
        )

    def _status_text(self, chat_id: int) -> str:
        subscription = self.storage.get_subscription(chat_id)
        timezone_name = self._get_chat_timezone_name(chat_id)
        rows = [("alerts", "off"), ("tz", timezone_name)]
        if subscription and subscription.enabled:
            region_scope = self._format_region_scope(subscription.region_filter)
            rows = [
                ("alerts", "active"),
                ("min mag", f"{subscription.min_magnitude:.1f}"),
                ("region", region_scope),
                ("tz", timezone_name),
            ]
        rows.extend(
            [
                ("feed", f"{self.storage.get_state('last_feed_event_count') or '0'} events"),
                ("sync", self._format_state_time(chat_id, self.storage.get_state("last_feed_sync_at") or "never")),
                ("poll", f"{self.config.usgs_poll_seconds}s"),
            ]
        )
        text = f"<b>Status</b>\n{self._format_rows(rows)}"
        if self._is_admin(chat_id):
            text += "\n\n<b>Admin tools</b>\nUse the buttons below to send a demo alert or inspect bot health."
        return text

    def _latest_text(self, chat_id: int) -> str:
        events = self.storage.get_latest_events(limit=5)
        return self._render_latest_events_text(chat_id, LATEST_LABEL, events)

    def _latest_subscribed_text(self, chat_id: int) -> str:
        subscription = self.storage.get_subscription(chat_id)
        if not subscription or not subscription.enabled:
            return (
                f"<b>{LATEST_SUBSCRIBED_LABEL}</b>\n"
                "Tap <b>Subscribe</b> first."
            )

        filters = self._decode_region_filters(subscription.region_filter)
        if not filters:
            return self._latest_text(chat_id).replace(LATEST_LABEL, LATEST_SUBSCRIBED_LABEL, 1)

        grouped_events = [
            (region, self.storage.get_latest_matching_events(0.0, [region], limit=5))
            for region in filters
        ]
        return self._render_grouped_latest_events_text(chat_id, LATEST_SUBSCRIBED_LABEL, grouped_events)

    def _render_latest_events_text(self, chat_id: int, title: str, events: list) -> str:
        if not events:
            return f"<b>{html.escape(title)}</b>\nNothing stored yet."
        lines = [f"<b>{html.escape(title)}</b>", ""]
        lines.extend(self._render_latest_event_lines(chat_id, events))
        return "\n".join(lines)

    def _render_grouped_latest_events_text(self, chat_id: int, title: str, grouped_events: list[tuple[str, list]]) -> str:
        non_empty_groups = [(region, events) for region, events in grouped_events if events]
        if not non_empty_groups:
            return f"<b>{html.escape(title)}</b>\nNothing stored yet that matches your current filters."

        lines = [f"<b>{html.escape(title)}</b>", ""]
        for index, (region, events) in enumerate(non_empty_groups):
            if index > 0:
                lines.append("")
            lines.append("=================================")
            lines.append(f"<b>{html.escape(self._region_display_label(region))}</b>")
            lines.extend(self._render_latest_event_lines(chat_id, events))
        return "\n".join(lines)

    def _render_latest_event_lines(self, chat_id: int, events: list) -> list[str]:
        lines: list[str] = []
        for event in events:
            lines.append(f"<code>M{self._format_magnitude(event.magnitude)}  {self._format_summary_time(chat_id, event.event_time)}</code>")
            lines.append(html.escape(self._truncate(event.place, 90)))
            lines.append("")
        return lines[:-1] if lines else lines

    def _region_display_label(self, region: str) -> str:
        flag = REGION_FLAGS.get(region)
        return f"{flag} {region}" if flag else region

    def _subscription_saved_text(self, min_magnitude: float, region_filter: str | None) -> str:
        region_scope = self._format_region_scope(region_filter)
        scope_line = (
            f"<b>Scope</b> {html.escape(region_scope)}"
            if region_filter
            else "<b>Scope</b> global feed"
        )
        return (
            "<b>Alerts On</b>\n"
            f"<b>Min mag</b> <code>M{min_magnitude:.1f}+</code>\n"
            f"{scope_line}"
        )

    def _subscribe_intro_text(self) -> str:
        return (
            f"<b>{SUBSCRIBE_LABEL}</b>\n"
            "Choose how you want alerts delivered.\n"
            "\n"
            f"<b>{SUBSCRIBE_ALL_OPTION_LABEL}</b> - every quake at <code>M{self.config.default_min_magnitude:.1f}+</code>\n"
            f"<b>{SUBSCRIBE_REGION_OPTION_LABEL}</b> - pick continent, then countries or regions"
        )

    def _region_intro_text(self) -> str:
        return (
            "<b>Region Alerts</b>\n"
            "Pick a continent first. Then tap countries or regions to toggle them, and press Confirm ✅.\n"
            "\n"
            f"Default threshold: <code>M{self.config.default_min_magnitude:.1f}+</code>"
        )

    def _format_rows(self, rows: list[tuple[str, str]]) -> str:
        width = max(len(label) for label, _ in rows)
        return "\n".join(
            f"<code>{html.escape(label.ljust(width))}</code> {html.escape(value)}" for label, value in rows
        )

    def _link(self, label: str, url: str) -> str:
        return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'

    def _format_event_time(self, chat_id: int, event_time: datetime) -> str:
        local_time = event_time.astimezone(self._get_chat_timezone(chat_id))
        return local_time.strftime("%Y-%m-%d %H:%M %Z")

    def _format_summary_time(self, chat_id: int, event_time: datetime) -> str:
        local_time = event_time.astimezone(self._get_chat_timezone(chat_id))
        return local_time.strftime("%m-%d %H:%M %Z")

    def _format_state_time(self, chat_id: int, timestamp: str) -> str:
        if timestamp == "never":
            return "never"
        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError:
            return timestamp
        return parsed.astimezone(self._get_chat_timezone(chat_id)).strftime("%Y-%m-%d %H:%M %Z")

    def _truncate(self, value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return value[: max(0, limit - 1)].rstrip() + "…"
