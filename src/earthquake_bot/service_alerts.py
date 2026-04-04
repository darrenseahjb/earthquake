from __future__ import annotations

import html
import logging


logger = logging.getLogger(__name__)


class ServiceAlertMixin:
    def _notify_matching_subscribers(
        self,
        event,
        subscriptions: list | None = None,
        is_update: bool = False,
    ) -> None:
        subscribers = subscriptions if subscriptions is not None else self.storage.list_active_subscriptions()
        for subscription in subscribers:
            if self._event_matches_subscription(event, subscription):
                dedupe_key = f"alert:{event.event_id}:{subscription.chat_id}:{event.updated_ms}"
                queued = self._enqueue_event_alert(subscription.chat_id, event, is_update, dedupe_key)
                if not queued:
                    logger.debug(
                        "Skipped duplicate alert enqueue for event %s and chat %s.",
                        event.event_id,
                        subscription.chat_id,
                    )

    def _enqueue_event_alert(
        self,
        chat_id: int,
        event,
        is_update: bool,
        dedupe_key: str,
        title_override: str | None = None,
        advisories_override: list[str] | None = None,
        source_caption_override: str | None = None,
    ) -> bool:
        if self._should_send_alert_card(event):
            card_bytes = self._render_event_alert_card(
                chat_id,
                event,
                is_update,
                title_override=title_override,
                advisories_override=advisories_override,
            )
            if card_bytes is not None:
                return self.storage.enqueue_outbound_message(
                    chat_id,
                    source_caption_override if source_caption_override is not None else self._event_source_caption(event),
                    parse_mode="HTML",
                    reply_markup=self._quick_actions_keyboard(),
                    category="alert",
                    dedupe_key=dedupe_key,
                    message_kind="photo",
                    media=card_bytes,
                    media_filename=f"quake-{event.event_id}.png",
                )

        return self.storage.enqueue_outbound_message(
            chat_id,
            self._format_event_message(
                chat_id,
                event,
                is_update=is_update,
                title_override=title_override,
                advisories_override=advisories_override,
                source_caption_override=source_caption_override,
            ),
            parse_mode="HTML",
            reply_markup=self._quick_actions_keyboard(),
            category="alert",
            dedupe_key=dedupe_key,
        )

    def _should_send_alert_card(self, event) -> bool:
        return (
            (event.magnitude or 0.0) >= 5.0
            and event.latitude is not None
            and event.longitude is not None
        )

    def _render_event_alert_card(
        self,
        chat_id: int,
        event,
        is_update: bool,
        title_override: str | None = None,
        advisories_override: list[str] | None = None,
    ) -> bytes | None:
        try:
            return self.alert_card_renderer.render_card(
                event,
                self._format_event_time(chat_id, event.event_time),
                title_override or self._event_title(event, is_update),
                advisories_override if advisories_override is not None else self._event_advisories(event),
            )
        except Exception:
            logger.exception("Failed to render alert card for event %s.", event.event_id)
            return None

    def _event_source_caption(self, event) -> str:
        links: list[str] = []
        if event.event_url:
            links.append(self._link("USGS", event.event_url))
        if event.shakemap_url:
            links.append(self._link("ShakeMap", event.shakemap_url))
        if not links:
            return ""
        return f"<b>Official source:</b> {' | '.join(links)}"

    def _event_matches_subscription(self, event, subscription) -> bool:
        magnitude = event.magnitude or 0.0
        if magnitude < subscription.min_magnitude:
            return False

        filters = self._decode_region_filters(subscription.region_filter)
        if not filters:
            return True

        place = (event.place or "").lower()
        return any(filter_value.lower() in place for filter_value in filters)

    def _should_send_update_alert(self, previous_event, updated_event) -> bool:
        previous_magnitude = previous_event.magnitude or 0.0
        updated_magnitude = updated_event.magnitude or 0.0
        if abs(updated_magnitude - previous_magnitude) >= 0.5:
            return True

        previous_alert_level = (previous_event.alert_level or "").lower()
        updated_alert_level = (updated_event.alert_level or "").lower()
        if updated_alert_level in {"orange", "red"} and updated_alert_level != previous_alert_level:
            return True

        if updated_event.tsunami and not previous_event.tsunami:
            return True

        return False

    def _format_event_message(
        self,
        chat_id: int,
        event,
        is_update: bool,
        title_override: str | None = None,
        advisories_override: list[str] | None = None,
        source_caption_override: str | None = None,
    ) -> str:
        lines = [f"🚨 <b>{html.escape((title_override or self._event_title(event, is_update)).upper())}</b>"]

        advisories = advisories_override if advisories_override is not None else self._event_advisories(event)
        for advisory in advisories:
            lines.append(f"<i><b>{html.escape(advisory.upper())}</b></i>")

        lines.append(
            f"<code>M{html.escape(self._format_magnitude(event.magnitude))}  "
            f"{html.escape(self._format_event_time(chat_id, event.event_time))}</code>"
        )
        lines.append(f"<b>{html.escape(event.place)}</b>")

        rows: list[tuple[str, str]] = []
        if event.depth_km is not None:
            rows.append(("depth", f"{event.depth_km:.1f} km"))
        if event.alert_level:
            rows.append(("alert", self._format_alert_level(event.alert_level)))
        if event.max_mmi is not None:
            rows.append(("mmi", f"{event.max_mmi:.1f}"))
        if event.significance is not None:
            rows.append(("sig", str(event.significance)))
        if rows:
            lines.append(self._format_rows(rows))

        source_caption = source_caption_override
        if source_caption is None:
            links: list[str] = []
            if event.event_url:
                links.append(self._link("USGS", event.event_url))
            if event.shakemap_url:
                links.append(self._link("ShakeMap", event.shakemap_url))
            if links:
                source_caption = f"<b>Official source:</b> {' | '.join(links)}"
        if source_caption:
            lines.append(source_caption)

        return "\n".join(lines)

    def _format_magnitude(self, magnitude: float | None) -> str:
        if magnitude is None:
            return "unknown"
        return f"{magnitude:.1f}"

    def _event_title(self, event, is_update: bool) -> str:
        magnitude = event.magnitude or 0.0
        alert_level = (event.alert_level or "").lower()

        if alert_level in {"red", "orange"}:
            base = f"{alert_level.title()} Alert"
            if magnitude >= 6.5:
                base = f"{base} Major Quake"
            return f"{base} Update" if is_update else base

        if magnitude >= 7.0:
            return "Severe Quake Update" if is_update else "Severe Quake Alert"
        if magnitude >= 6.0:
            return "Major Quake Update" if is_update else "Major Quake Alert"
        if magnitude >= 5.0:
            return "Strong Quake Update" if is_update else "Strong Quake Alert"

        return "Earthquake Update" if is_update else "Earthquake Alert"

    def _event_advisories(self, event) -> list[str]:
        advisories: list[str] = []
        magnitude = event.magnitude or 0.0
        alert_level = (event.alert_level or "").lower()

        if alert_level == "red":
            advisories.append("Highest impact risk. Prioritize official emergency guidance.")
        elif alert_level == "orange":
            advisories.append("Elevated impact risk. Check official guidance and local updates.")
        elif magnitude >= 7.0:
            advisories.append("Potentially destructive shaking. Follow official guidance immediately.")
        elif magnitude >= 6.0:
            advisories.append("Potentially damaging quake. Expect aftershocks and monitor official updates.")
        elif magnitude >= 5.0:
            advisories.append("Stay alert for local updates and aftershocks.")

        if event.tsunami:
            advisories.append("Tsunami note: Check official coastal advisories now.")

        return advisories

    def _format_alert_level(self, alert_level: str) -> str:
        lowered = alert_level.lower()
        if lowered == "red":
            return "RED | highest impact risk"
        if lowered == "orange":
            return "ORANGE | elevated impact risk"
        if lowered == "yellow":
            return "YELLOW | limited impact"
        if lowered == "green":
            return "GREEN | minor impact"
        return alert_level.upper()
