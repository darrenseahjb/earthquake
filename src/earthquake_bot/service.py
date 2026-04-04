from __future__ import annotations

import html
import json
import logging
import re
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from earthquake_bot.alert_cards import AlertCardRenderer
from earthquake_bot.config import Config
from earthquake_bot.models import EarthquakeEvent, Subscription
from earthquake_bot.service_admin import ServiceAdminMixin
from earthquake_bot.service_alerts import ServiceAlertMixin
from earthquake_bot.service_constants import (
    BACK_LABEL,
    CANCEL_LABEL,
    CONFIRM_LABEL,
    CONTINENT_COUNTRIES,
    LATEST_LABEL,
    LATEST_SUBSCRIBED_LABEL,
    SELECTED_PREFIX,
    STATUS_LABEL,
    SUBSCRIBE_ALL_OPTION_LABEL,
    SUBSCRIBE_LABEL,
    SUBSCRIBE_REGION_OPTION_LABEL,
    TIMEZONE_COUNTRY_PAGE_SIZE,
    TIMEZONE_LABEL,
    TIMEZONE_ZONE_PAGE_SIZE,
    UNSUBSCRIBE_LABEL,
)
from earthquake_bot.service_text import ServiceTextMixin
from earthquake_bot.storage import Storage
from earthquake_bot.telegram_api import TelegramApiError, TelegramClient, TelegramUpdate
from earthquake_bot.timezone_catalog import (
    countries_for_region,
    country_button_label,
    get_country,
    gmt_label_for_timezone,
    list_regions,
    region_label,
    timezone_label,
)
from earthquake_bot.usgs import USGSClient, UsgsClientError


logger = logging.getLogger(__name__)


class EarthquakeBotService(ServiceAdminMixin, ServiceTextMixin, ServiceAlertMixin):
    def __init__(
        self,
        config: Config,
        storage: Storage,
        usgs_client: USGSClient,
        telegram_client: TelegramClient,
    ) -> None:
        self.config = config
        self.storage = storage
        self.usgs_client = usgs_client
        self.telegram_client = telegram_client
        self.alert_card_renderer = AlertCardRenderer()
        self._region_picker_lock = threading.Lock()
        self._region_picker_contexts: dict[int, dict[str, object]] = {}
        self._timezone_cache_lock = threading.Lock()
        self._chat_timezones: dict[int, str | None] = {}
        self._inline_message_lock = threading.Lock()
        self._inline_message_states: dict[tuple[int, int], tuple[str, str]] = {}

    def handle_update(self, update: TelegramUpdate) -> None:
        if update.callback_data:
            if self._handle_timezone_callback(update):
                return
            if not self._has_chat_timezone(update.chat_id):
                self._answer_callback(update, "Set your timezone first.")
                if update.message_id is not None:
                    self._edit_inline_message(
                        update.chat_id,
                        update.message_id,
                        self._timezone_intro_text(update.chat_id, required=True),
                        self._timezone_region_keyboard(required=True),
                    )
                else:
                    self._send_timezone_picker(update.chat_id, required=True)
                return
            if self._handle_subscribe_callback(update):
                return
            if self._handle_region_callback(update):
                return
            if self._handle_admin_callback(update):
                return
            if update.callback_query_id:
                self.telegram_client.answer_callback_query(update.callback_query_id)
            return

        text = self._normalize_quick_action(update.text.strip())
        if not text.startswith("/"):
            if self._handle_region_selection(update):
                return
            if not self._has_chat_timezone(update.chat_id):
                self._send_timezone_picker(update.chat_id, required=True)
                return
            self.telegram_client.send_message(
                update.chat_id,
                "Use the buttons below. If they disappear, send /help.",
                reply_markup=self._quick_actions_keyboard(),
            )
            return

        command, _, remainder = text.partition(" ")
        command = command.partition("@")[0]
        args = remainder.strip()
        command, alias_args = self._normalize_subscribe_command(command)
        if alias_args:
            args = alias_args if not args else f"{alias_args} {args}".strip()

        lowered_command = command.lower()
        self.storage.clear_chat_context(update.chat_id)
        self._clear_region_picker_context(update.chat_id)
        if lowered_command not in {"/start", "/timezone"} and not self._has_chat_timezone(update.chat_id):
            self._send_timezone_picker(update.chat_id, required=True)
            return

        match lowered_command:
            case "/start":
                if self._has_chat_timezone(update.chat_id):
                    self.telegram_client.send_message(
                        update.chat_id,
                        self._start_text(),
                        parse_mode="HTML",
                        reply_markup=self._quick_actions_keyboard(),
                    )
                else:
                    self._send_timezone_picker(update.chat_id, onboarding=True)
            case "/help":
                self.telegram_client.send_message(
                    update.chat_id,
                    self._help_text(),
                    parse_mode="HTML",
                    reply_markup=self._quick_actions_keyboard(),
                )
            case "/region":
                self._set_region_picker_context(
                    update.chat_id,
                    "choose_continent",
                    {"selected": self._get_region_picker_selection(update.chat_id)},
                )
                self.telegram_client.send_message(
                    update.chat_id,
                    self._region_intro_text(),
                    parse_mode="HTML",
                    reply_markup=self._continent_inline_keyboard(),
                )
            case "/timezone":
                had_timezone = self._has_chat_timezone(update.chat_id)
                if args:
                    message = self._handle_timezone_command(update.chat_id, args)
                    has_timezone = self._has_chat_timezone(update.chat_id)
                    reply_markup = (
                        self._quick_actions_keyboard()
                        if has_timezone
                        else self._timezone_region_keyboard(required=True)
                    )
                    self.telegram_client.send_message(
                        update.chat_id,
                        message,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                    )
                    if not had_timezone and has_timezone:
                        self.telegram_client.send_message(
                            update.chat_id,
                            self._start_text(),
                            parse_mode="HTML",
                            reply_markup=self._quick_actions_keyboard(),
                        )
                else:
                    self._send_timezone_picker(update.chat_id, onboarding=not had_timezone)
            case "/subscribe":
                if args:
                    min_magnitude, region_filter = self._parse_subscription_args(args)
                    self.storage.upsert_subscription(update.chat_id, min_magnitude, region_filter)
                    self.storage.clear_chat_context(update.chat_id)
                    self._clear_region_picker_context(update.chat_id)
                    self.telegram_client.send_message(
                        update.chat_id,
                        self._subscription_saved_text(min_magnitude, region_filter),
                        parse_mode="HTML",
                        reply_markup=self._quick_actions_keyboard(),
                    )
                else:
                    self.telegram_client.send_message(
                        update.chat_id,
                        self._subscribe_intro_text(),
                        parse_mode="HTML",
                        reply_markup=self._subscribe_mode_keyboard(),
                    )
            case "/subscribe_all":
                self.storage.upsert_subscription(update.chat_id, self.config.default_min_magnitude, None)
                self.telegram_client.send_message(
                    update.chat_id,
                    self._subscription_saved_text(self.config.default_min_magnitude, None),
                    parse_mode="HTML",
                    reply_markup=self._quick_actions_keyboard(),
                )
            case "/unsubscribe":
                removed = self.storage.disable_subscription(update.chat_id)
                self.storage.clear_chat_context(update.chat_id)
                self._clear_region_picker_context(update.chat_id)
                if removed:
                    message = "<b>Alerts Paused</b>\nTap <b>Subscribe</b> any time to turn alerts back on."
                else:
                    message = "<b>No Active Alerts</b>\nThis chat is not currently subscribed."
                self.telegram_client.send_message(
                    update.chat_id,
                    message,
                    parse_mode="HTML",
                    reply_markup=self._quick_actions_keyboard(),
                )
            case "/status":
                self.telegram_client.send_message(
                    update.chat_id,
                    self._status_text(update.chat_id),
                    parse_mode="HTML",
                    reply_markup=self._status_reply_markup(update.chat_id),
                )
            case "/latest":
                self.telegram_client.send_message(
                    update.chat_id,
                    self._latest_text(update.chat_id),
                    parse_mode="HTML",
                    reply_markup=self._quick_actions_keyboard(),
                )
            case "/latest_subscribed":
                self.telegram_client.send_message(
                    update.chat_id,
                    self._latest_subscribed_text(update.chat_id),
                    parse_mode="HTML",
                    reply_markup=self._quick_actions_keyboard(),
                )
            case "/health":
                if self._is_admin(update.chat_id):
                    self.telegram_client.send_message(
                        update.chat_id,
                        self._health_text(update.chat_id),
                        parse_mode="HTML",
                        reply_markup=self._quick_actions_keyboard(),
                    )
                else:
                    self.telegram_client.send_message(
                        update.chat_id,
                        "<b>Admin Only</b>\nThis tool is only available to configured admin chats.",
                        parse_mode="HTML",
                        reply_markup=self._quick_actions_keyboard(),
                    )
            case "/testalert":
                if self._is_admin(update.chat_id):
                    queued = self._queue_admin_test_alert(update.chat_id)
                    message = (
                        "<b>Demo Alert Queued</b>\nA clearly marked admin-only preview is on the way."
                        if queued
                        else "<b>Demo Alert Skipped</b>\nThe preview alert could not be queued."
                    )
                else:
                    message = "<b>Admin Only</b>\nThis tool is only available to configured admin chats."
                self.telegram_client.send_message(
                    update.chat_id,
                    message,
                    parse_mode="HTML",
                    reply_markup=self._quick_actions_keyboard(),
                )
            case "/broadcast":
                if self._is_admin(update.chat_id):
                    message = self._broadcast_admin_message(args)
                else:
                    message = "<b>Admin Only</b>\nThis tool is only available to configured admin chats."
                self.telegram_client.send_message(
                    update.chat_id,
                    message,
                    parse_mode="HTML",
                    reply_markup=self._quick_actions_keyboard(),
                )
            case _:
                self.telegram_client.send_message(
                    update.chat_id,
                    "Unknown command. Use the buttons below. If needed, send <code>/help</code>.",
                    parse_mode="HTML",
                    reply_markup=self._quick_actions_keyboard(),
                )

    def sync_earthquakes(self) -> int:
        try:
            features = self.usgs_client.fetch_summary_feed()
        except UsgsClientError:
            logger.exception("Failed to fetch the USGS summary feed.")
            return 0

        candidate_ids = [
            str(feature.get("id", "")).strip()
            for feature in features
            if str(feature.get("id", "")).strip()
        ]
        known_updates = self.storage.get_known_updated_ms_map(candidate_ids)
        active_subscriptions = self.storage.list_active_subscriptions()
        changed_events = 0
        for feature in features:
            event_id = str(feature.get("id", "")).strip()
            properties = feature.get("properties") or {}
            updated_ms = int(properties.get("updated", 0) or 0)
            detail_url = str(properties.get("detail", "")).strip()

            if not event_id or not detail_url:
                continue

            known_updated_ms = known_updates.get(event_id)
            if known_updated_ms is not None and updated_ms <= known_updated_ms:
                continue

            previous_event = self.storage.get_event(event_id) if known_updated_ms is not None else None

            try:
                event = self.usgs_client.fetch_detail(detail_url)
            except Exception:
                logger.exception("Failed to fetch or parse detail for event %s.", event_id)
                continue

            is_update = known_updated_ms is not None
            self.storage.upsert_event(event)
            should_notify = not is_update or self._should_send_update_alert(previous_event, event)
            if should_notify:
                self._notify_matching_subscribers(event, active_subscriptions, is_update=is_update)
            known_updates[event_id] = event.updated_ms
            changed_events += 1

        self.storage.set_state("last_feed_sync_at", datetime.now(timezone.utc).isoformat())
        self.storage.set_state("last_feed_event_count", str(len(features)))
        return changed_events

























    def _handle_timezone_command(self, chat_id: int, args: str) -> str:
        timezone_name = args.strip()
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            return (
                "<b>Unknown Timezone</b>\n"
                "Tap <b>Edit Timezone</b> to browse by region and country,\n"
                "or send an IANA timezone like <code>Asia/Singapore</code>."
            )

        self._set_chat_timezone_name(chat_id, timezone_name)
        return (
            "<b>Timezone Updated</b>\n"
            f"Times will now display in <code>{html.escape(timezone_name)}</code> "
            f"({html.escape(gmt_label_for_timezone(timezone_name))})."
        )

    def _has_chat_timezone(self, chat_id: int) -> bool:
        return self._get_stored_chat_timezone_name(chat_id) is not None

    def _send_timezone_picker(self, chat_id: int, onboarding: bool = False, required: bool = False) -> None:
        text = self._timezone_intro_text(chat_id, onboarding=onboarding, required=required)
        required_picker = required or (onboarding and not self._has_chat_timezone(chat_id))
        self.telegram_client.send_message(
            chat_id,
            text,
            parse_mode="HTML",
            reply_markup=self._timezone_region_keyboard(required=required_picker),
        )

    def _timezone_intro_text(self, chat_id: int, onboarding: bool = False, required: bool = False) -> str:
        if onboarding and not self._has_chat_timezone(chat_id):
            return (
                "<b>Earthquake Monitor</b>\n"
                "Set your timezone first so every quake time and alert matches your local clock.\n"
                "\n"
                "<b>Pick a region</b>"
            )

        if required and not self._has_chat_timezone(chat_id):
            return (
                "<b>Timezone Required</b>\n"
                "Set your timezone first, then we can unlock alerts and recent quakes.\n"
                "\n"
                "<b>Pick a region</b>"
            )

        current_timezone = self._get_chat_timezone_name(chat_id)
        return (
            "<b>Timezone</b>\n"
            f"Current zone: <code>{html.escape(current_timezone)}</code>\n"
            f"Current offset: <code>{html.escape(gmt_label_for_timezone(current_timezone))}</code>\n"
            "\n"
            "<b>Pick a region</b>"
        )

    def _timezone_region_keyboard(self, required: bool = False) -> dict[str, object]:
        regions = list_regions()
        rows: list[list[dict[str, str]]] = []
        row: list[dict[str, str]] = []
        for slug, label in regions:
            row.append(self._inline_button(label, self._timezone_callback("region", slug, "0")))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        if not required:
            rows.append([self._inline_button(CANCEL_LABEL, self._timezone_callback("cancel"))])
        return {"inline_keyboard": rows}

    def _timezone_country_keyboard(self, region_slug: str, page: int, required: bool = False) -> dict[str, object]:
        countries = countries_for_region(region_slug)
        page_items, page, total_pages = self._paginate(countries, page, TIMEZONE_COUNTRY_PAGE_SIZE)

        rows = [
            [
                self._inline_button(
                    country_button_label(country),
                    self._timezone_callback("country", country.code, region_slug, str(page)),
                )
            ]
            for country in page_items
        ]

        nav_row: list[dict[str, str]] = []
        if page > 0:
            nav_row.append(self._inline_button("Prev", self._timezone_callback("region", region_slug, str(page - 1))))
        if page < total_pages - 1:
            nav_row.append(self._inline_button("Next", self._timezone_callback("region", region_slug, str(page + 1))))
        if nav_row:
            rows.append(nav_row)
        footer = [self._inline_button(BACK_LABEL, self._timezone_callback("menu"))]
        if not required:
            footer.append(self._inline_button(CANCEL_LABEL, self._timezone_callback("cancel")))
        rows.append(footer)
        return {"inline_keyboard": rows}

    def _timezone_country_text(self, region_slug: str, page: int) -> str:
        countries = countries_for_region(region_slug)
        _, page, total_pages = self._paginate(countries, page, TIMEZONE_COUNTRY_PAGE_SIZE)
        return (
            f"<b>{html.escape(region_label(region_slug))}</b>\n"
            "Choose your country or territory.\n"
            "GMT values reflect the current local offset and may shift with daylight saving time.\n"
            f"\n<b>Page</b> {page + 1}/{total_pages}"
        )

    def _timezone_zone_keyboard(
        self,
        country_code: str,
        region_slug: str,
        country_page: int,
        zone_page: int,
        required: bool = False,
    ) -> dict[str, object]:
        country = get_country(country_code)
        if country is None:
            return {
                "inline_keyboard": [[self._inline_button(BACK_LABEL, self._timezone_callback("menu"))]]
            }

        indexed_zones = list(enumerate(country.timezones))
        page_items, zone_page, total_pages = self._paginate(indexed_zones, zone_page, TIMEZONE_ZONE_PAGE_SIZE)
        rows = [
            [self._inline_button(timezone_label(country, index), self._timezone_callback("pick", country.code, str(index)))]
            for index, _ in page_items
        ]

        nav_row: list[dict[str, str]] = []
        if zone_page > 0:
            nav_row.append(
                self._inline_button(
                    "Prev",
                    self._timezone_callback("zone", country.code, region_slug, str(country_page), str(zone_page - 1)),
                )
            )
        if zone_page < total_pages - 1:
            nav_row.append(
                self._inline_button(
                    "Next",
                    self._timezone_callback("zone", country.code, region_slug, str(country_page), str(zone_page + 1)),
                )
            )
        if nav_row:
            rows.append(nav_row)
        footer = [self._inline_button(BACK_LABEL, self._timezone_callback("region", region_slug, str(country_page)))]
        if not required:
            footer.append(self._inline_button(CANCEL_LABEL, self._timezone_callback("cancel")))
        rows.append(footer)
        return {"inline_keyboard": rows}

    def _timezone_zone_text(self, country_code: str, zone_page: int) -> str:
        country = get_country(country_code)
        if country is None:
            return "<b>Timezone</b>\nChoose the timezone that matches your local clock."

        _, zone_page, total_pages = self._paginate(list(enumerate(country.timezones)), zone_page, TIMEZONE_ZONE_PAGE_SIZE)
        return (
            f"<b>{html.escape(country.name)}</b>\n"
            "Choose the timezone that matches your city or local clock.\n"
            f"\n<b>Page</b> {zone_page + 1}/{total_pages}"
        )

    def _handle_timezone_callback(self, update: TelegramUpdate) -> bool:
        callback_data = update.callback_data or ""
        if not callback_data.startswith("timezone|"):
            return False

        if update.message_id is None:
            self._answer_callback(update, "Tap Edit Timezone to start again.")
            return True

        parts = callback_data.split("|")
        action = parts[1] if len(parts) > 1 else ""
        required = not self._has_chat_timezone(update.chat_id)

        if action == "cancel":
            if required:
                self._answer_callback(update, "Timezone is required.")
                self._edit_inline_message(
                    update.chat_id,
                    update.message_id,
                    self._timezone_intro_text(update.chat_id, required=True),
                    self._timezone_region_keyboard(required=True),
                )
                return True
            self._answer_callback(update, "Cancelled.")
            self._edit_inline_message(update.chat_id, update.message_id, "<b>Timezone Setup Cancelled</b>")
            return True

        if action == "menu":
            self._answer_callback(update)
            self._edit_inline_message(
                update.chat_id,
                update.message_id,
                self._timezone_intro_text(update.chat_id, required=required),
                self._timezone_region_keyboard(required=required),
            )
            return True

        if action == "region":
            region_slug = parts[2] if len(parts) > 2 else ""
            page = self._parse_int(parts[3] if len(parts) > 3 else "0")
            if not countries_for_region(region_slug):
                self._answer_callback(update, "Unknown region.")
                return True

            self._answer_callback(update)
            self._edit_inline_message(
                update.chat_id,
                update.message_id,
                self._timezone_country_text(region_slug, page),
                self._timezone_country_keyboard(region_slug, page, required=required),
            )
            return True

        if action == "country":
            country_code = parts[2] if len(parts) > 2 else ""
            region_slug = parts[3] if len(parts) > 3 else ""
            country_page = self._parse_int(parts[4] if len(parts) > 4 else "0")
            country = get_country(country_code)
            if country is None:
                self._answer_callback(update, "Unknown country.")
                return True

            if len(country.timezones) == 1:
                self._answer_callback(update, "Timezone saved.")
                self._save_timezone_selection(update.chat_id, update.message_id, country.timezones[0])
                return True

            self._answer_callback(update)
            self._edit_inline_message(
                update.chat_id,
                update.message_id,
                self._timezone_zone_text(country_code, 0),
                self._timezone_zone_keyboard(country_code, region_slug, country_page, 0, required=required),
            )
            return True

        if action == "zone":
            country_code = parts[2] if len(parts) > 2 else ""
            region_slug = parts[3] if len(parts) > 3 else ""
            country_page = self._parse_int(parts[4] if len(parts) > 4 else "0")
            zone_page = self._parse_int(parts[5] if len(parts) > 5 else "0")
            country = get_country(country_code)
            if country is None:
                self._answer_callback(update, "Unknown country.")
                return True

            self._answer_callback(update)
            self._edit_inline_message(
                update.chat_id,
                update.message_id,
                self._timezone_zone_text(country_code, zone_page),
                self._timezone_zone_keyboard(
                    country_code,
                    region_slug,
                    country_page,
                    zone_page,
                    required=required,
                ),
            )
            return True

        if action == "pick":
            country_code = parts[2] if len(parts) > 2 else ""
            zone_index = self._parse_int(parts[3] if len(parts) > 3 else "0")
            country = get_country(country_code)
            if country is None or zone_index >= len(country.timezones):
                self._answer_callback(update, "Unknown timezone.")
                return True

            self._answer_callback(update, "Timezone saved.")
            self._save_timezone_selection(update.chat_id, update.message_id, country.timezones[zone_index])
            return True

        self._answer_callback(update, "Tap Edit Timezone to start again.")
        return True

    def _save_timezone_selection(self, chat_id: int, message_id: int, timezone_name: str) -> None:
        had_timezone = self._has_chat_timezone(chat_id)
        self._set_chat_timezone_name(chat_id, timezone_name)
        self._edit_inline_message(
            chat_id,
            message_id,
            (
                "<b>Timezone Updated</b>\n"
                f"<code>{html.escape(timezone_name)}</code>\n"
                f"{html.escape(gmt_label_for_timezone(timezone_name))}"
            ),
        )
        if not had_timezone:
            self.telegram_client.send_message(
                chat_id,
                self._start_text(),
                parse_mode="HTML",
                reply_markup=self._quick_actions_keyboard(),
            )

    def _timezone_callback(self, action: str, *parts: str) -> str:
        filtered_parts = [part for part in parts if part != ""]
        return "|".join(["timezone", action, *filtered_parts])

    def _edit_inline_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, object] | None = None,
    ) -> None:
        markup = reply_markup if reply_markup is not None else {"inline_keyboard": []}
        cache_key = (chat_id, message_id)
        fingerprint = self._inline_message_fingerprint(text, markup)
        with self._inline_message_lock:
            if self._inline_message_states.get(cache_key) == fingerprint:
                logger.debug(
                    "Skipped cached inline edit for chat %s message %s",
                    chat_id,
                    message_id,
                )
                return
        try:
            self.telegram_client.edit_message(
                chat_id,
                message_id,
                text,
                parse_mode="HTML",
                reply_markup=markup,
            )
        except TelegramApiError as exc:
            description = (exc.description or "").lower()
            if exc.error_code == 400 and "message is not modified" in description:
                logger.debug(
                    "Skipped no-op inline edit for chat %s message %s",
                    chat_id,
                    message_id,
                )
                with self._inline_message_lock:
                    self._inline_message_states[cache_key] = fingerprint
                return
            raise
        with self._inline_message_lock:
            self._inline_message_states[cache_key] = fingerprint

    def _inline_message_fingerprint(
        self,
        text: str,
        reply_markup: dict[str, object],
    ) -> tuple[str, str]:
        return (
            text,
            json.dumps(reply_markup, sort_keys=True, separators=(",", ":")),
        )

    def _paginate(self, items: list[object] | tuple[object, ...], page: int, page_size: int) -> tuple[list[object], int, int]:
        total_items = max(1, len(items))
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        safe_page = min(max(page, 0), total_pages - 1)
        start = safe_page * page_size
        end = start + page_size
        return list(items[start:end]), safe_page, total_pages

    def _parse_int(self, raw_value: str) -> int:
        try:
            return int(raw_value)
        except ValueError:
            return 0

    def _parse_subscription_args(self, args: str) -> tuple[float, str | None]:
        if not args:
            return self.config.default_min_magnitude, None

        tokens = args.split()
        first_token = tokens[0]

        try:
            min_magnitude = float(first_token)
            region_filter = " ".join(tokens[1:]).strip() or None
            return min_magnitude, region_filter
        except ValueError:
            return self.config.default_min_magnitude, args.strip() or None

    def _normalize_subscribe_command(self, command: str) -> tuple[str, str]:
        lowered_command = command.lower()
        if not lowered_command.startswith("/subscribe_"):
            return lowered_command, ""

        suffix = lowered_command.removeprefix("/subscribe_").strip("_")
        if not suffix:
            return "/subscribe", ""

        tokens = [token for token in suffix.split("_") if token]
        if not tokens:
            return "/subscribe", ""

        magnitude, consumed = self._extract_alias_magnitude(tokens)
        region_tokens = tokens[consumed:]
        region_filter = " ".join(region_tokens).strip()

        parts: list[str] = []
        if magnitude is not None:
            parts.append(magnitude)
        if region_filter:
            parts.append(region_filter)
        return "/subscribe", " ".join(parts)

    def _extract_alias_magnitude(self, tokens: list[str]) -> tuple[str | None, int]:
        if not tokens:
            return None, 0

        if re.fullmatch(r"\d+", tokens[0]):
            if len(tokens) >= 2 and re.fullmatch(r"\d+", tokens[1]):
                return f"{tokens[0]}.{tokens[1]}", 2
            return tokens[0], 1

        return None, 0













    def _matches_action_text(self, text: str, label: str) -> bool:
        lowered = text.casefold()
        if lowered == label.casefold():
            return True
        plain_label = label.split(" ", 1)[0]
        return lowered == plain_label.casefold()

    def _get_region_picker_context(self, chat_id: int) -> dict[str, object] | None:
        with self._region_picker_lock:
            context = self._region_picker_contexts.get(chat_id)
        if context is not None:
            return context

        legacy_context = self.storage.get_chat_context(chat_id)
        if legacy_context and str(legacy_context.get("step", "")) in {"choose_continent", "choose_country"}:
            with self._region_picker_lock:
                self._region_picker_contexts[chat_id] = legacy_context
            self.storage.clear_chat_context(chat_id)
            return legacy_context
        return None

    def _set_region_picker_context(
        self,
        chat_id: int,
        step: str,
        value: object | None = None,
    ) -> None:
        with self._region_picker_lock:
            self._region_picker_contexts[chat_id] = {"step": step, "value": value}

    def _clear_region_picker_context(self, chat_id: int) -> None:
        with self._region_picker_lock:
            self._region_picker_contexts.pop(chat_id, None)

    def _handle_region_selection(self, update: TelegramUpdate) -> bool:
        context = self._get_region_picker_context(update.chat_id)
        if not context:
            return False

        text = update.text.strip()
        lowered = text.casefold()

        if self._matches_action_text(text, CANCEL_LABEL):
            self._clear_region_picker_context(update.chat_id)
            self.telegram_client.send_message(
                update.chat_id,
                "<b>Region Setup Cancelled</b>",
                parse_mode="HTML",
                reply_markup=self._quick_actions_keyboard(),
            )
            return True

        step = str(context.get("step", ""))

        if step == "choose_continent":
            value = context.get("value") or {}
            selected = [str(item) for item in value.get("selected", []) if isinstance(item, str)]
            continent = self._match_choice(text, CONTINENT_COUNTRIES.keys())
            if not continent:
                self.telegram_client.send_message(
                    update.chat_id,
                    "Pick a continent from the buttons below.",
                    reply_markup=self._continent_inline_keyboard(),
                )
                return True

            self._set_region_picker_context(
                update.chat_id,
                "choose_country",
                {"continent": continent, "selected": selected},
            )
            self.telegram_client.send_message(
                update.chat_id,
                self._country_prompt_text(continent, selected),
                parse_mode="HTML",
                reply_markup=self._country_inline_keyboard(continent, selected),
            )
            return True

        if step == "choose_country":
            value = context.get("value") or {}
            continent = str(value.get("continent") or "")
            selected = [str(item) for item in value.get("selected", []) if isinstance(item, str)]
            countries = CONTINENT_COUNTRIES.get(continent, [])

            if lowered == BACK_LABEL.casefold():
                self._set_region_picker_context(update.chat_id, "choose_continent", {"selected": selected})
                self.telegram_client.send_message(
                    update.chat_id,
                    self._region_intro_text(),
                    parse_mode="HTML",
                    reply_markup=self._continent_inline_keyboard(),
                )
                return True

            if self._matches_action_text(text, CONFIRM_LABEL):
                if not selected:
                    self.telegram_client.send_message(
                        update.chat_id,
                        "<b>Select At Least One</b>\nTap one or more countries, then press Confirm ✅.",
                        parse_mode="HTML",
                        reply_markup=self._country_inline_keyboard(continent, selected),
                    )
                    return True

                encoded_regions = self._encode_region_filters(selected)
                self._clear_region_picker_context(update.chat_id)
                self.storage.upsert_subscription(
                    update.chat_id,
                    self.config.default_min_magnitude,
                    encoded_regions,
                )
                self.telegram_client.send_message(
                    update.chat_id,
                    self._subscription_saved_text(self.config.default_min_magnitude, encoded_regions),
                    parse_mode="HTML",
                    reply_markup=self._quick_actions_keyboard(),
                )
                return True

            country = self._match_choice(text, countries)
            if not country:
                self.telegram_client.send_message(
                    update.chat_id,
                    "Tap countries to toggle them, then press Confirm ✅.",
                    reply_markup=self._country_inline_keyboard(continent, selected),
                )
                return True

            updated_selected = self._toggle_selection(selected, country)
            self._set_region_picker_context(
                update.chat_id,
                "choose_country",
                {"continent": continent, "selected": updated_selected},
            )
            self.telegram_client.send_message(
                update.chat_id,
                self._country_prompt_text(continent, updated_selected),
                parse_mode="HTML",
                reply_markup=self._country_inline_keyboard(continent, updated_selected),
            )
            return True

        return False

    def _handle_region_callback(self, update: TelegramUpdate) -> bool:
        callback_data = update.callback_data or ""
        if not callback_data.startswith("region|"):
            return False

        if update.message_id is None:
            self._answer_callback(update, "Tap Subscribe to start again.")
            return True

        action, first_arg, second_arg = self._parse_region_callback(callback_data)

        if action == "cancel":
            self._answer_callback(update, "Cancelled.")
            self._clear_region_picker_context(update.chat_id)
            self._edit_inline_message(update.chat_id, update.message_id, "<b>Region Setup Cancelled</b>")
            return True

        if action == "continent":
            continent = self._match_choice(first_arg, CONTINENT_COUNTRIES.keys())
            if not continent:
                self._answer_callback(update, "Unknown continent.")
                return True

            context = self._get_region_picker_context(update.chat_id) or {}
            existing_value = context.get("value") or {}
            selected = [str(item) for item in existing_value.get("selected", []) if isinstance(item, str)]
            self._answer_callback(update)
            self._set_region_picker_context(
                update.chat_id,
                "choose_country",
                {"continent": continent, "selected": selected},
            )
            self._edit_inline_message(
                update.chat_id,
                update.message_id,
                self._country_prompt_text(continent, selected),
                self._country_inline_keyboard(continent, selected),
            )
            return True

        context = self._get_region_picker_context(update.chat_id)
        if not context:
            self._answer_callback(update, "Tap Subscribe to start again.")
            return True

        step = str(context.get("step", ""))
        if step == "choose_continent" and action == "back":
            self._answer_callback(update)
            self._edit_inline_message(
                update.chat_id,
                update.message_id,
                self._region_intro_text(),
                self._continent_inline_keyboard(),
            )
            return True

        if step != "choose_country":
            self._answer_callback(update, "Tap Subscribe to start again.")
            return True

        value = context.get("value") or {}
        continent = str(value.get("continent") or "")
        selected = [str(item) for item in value.get("selected", []) if isinstance(item, str)]

        if action == "back":
            self._answer_callback(update)
            self._set_region_picker_context(update.chat_id, "choose_continent", {"selected": selected})
            self._edit_inline_message(
                update.chat_id,
                update.message_id,
                self._region_intro_text(),
                self._continent_inline_keyboard(),
            )
            return True

        if action == "confirm":
            if not selected:
                self._answer_callback(update, "Select at least one region.")
                return True

            self._answer_callback(update, "Alerts updated.")
            encoded_regions = self._encode_region_filters(selected)
            self._clear_region_picker_context(update.chat_id)
            self.storage.upsert_subscription(
                update.chat_id,
                self.config.default_min_magnitude,
                encoded_regions,
            )
            self._edit_inline_message(
                update.chat_id,
                update.message_id,
                self._subscription_saved_text(self.config.default_min_magnitude, encoded_regions),
            )
            return True

        if action == "toggle":
            countries = CONTINENT_COUNTRIES.get(continent, [])
            country = self._match_choice(second_arg, countries)
            if not country:
                self._answer_callback(update, "Unknown region.")
                return True

            self._answer_callback(update)
            updated_selected = self._toggle_selection(selected, country)
            self._set_region_picker_context(
                update.chat_id,
                "choose_country",
                {"continent": continent, "selected": updated_selected},
            )
            self._edit_inline_message(
                update.chat_id,
                update.message_id,
                self._country_prompt_text(continent, updated_selected),
                self._country_inline_keyboard(continent, updated_selected),
            )
            return True

        self._answer_callback(update, "Tap Subscribe to start again.")
        return True

    def _handle_subscribe_callback(self, update: TelegramUpdate) -> bool:
        callback_data = update.callback_data or ""
        if not callback_data.startswith("subscribe|"):
            return False

        if update.message_id is None:
            self._answer_callback(update, "Tap Subscribe to start again.")
            return True

        action = self._parse_subscribe_callback(callback_data)
        if action == "cancel":
            self._answer_callback(update, "Cancelled.")
            self._edit_inline_message(update.chat_id, update.message_id, "<b>Subscribe Cancelled</b>")
            return True

        if action == "all":
            self._answer_callback(update, "Global alerts on.")
            self.storage.upsert_subscription(update.chat_id, self.config.default_min_magnitude, None)
            self._edit_inline_message(
                update.chat_id,
                update.message_id,
                self._subscription_saved_text(self.config.default_min_magnitude, None),
            )
            return True

        if action == "region":
            self._answer_callback(update)
            self._set_region_picker_context(
                update.chat_id,
                "choose_continent",
                {"selected": self._get_region_picker_selection(update.chat_id)},
            )
            self._edit_inline_message(
                update.chat_id,
                update.message_id,
                self._region_intro_text(),
                self._continent_inline_keyboard(),
            )
            return True

        self._answer_callback(update, "Tap Subscribe to start again.")
        return True


    def _continent_inline_keyboard(self) -> dict[str, object]:
        continents = list(CONTINENT_COUNTRIES.keys())
        rows = [
            [
                self._inline_button(continents[0], self._region_callback("continent", continents[0])),
                self._inline_button(continents[1], self._region_callback("continent", continents[1])),
            ],
            [
                self._inline_button(continents[2], self._region_callback("continent", continents[2])),
                self._inline_button(continents[3], self._region_callback("continent", continents[3])),
            ],
            [
                self._inline_button(continents[4], self._region_callback("continent", continents[4])),
                self._inline_button(continents[5], self._region_callback("continent", continents[5])),
            ],
            [self._inline_button(CANCEL_LABEL, self._region_callback("cancel"))],
        ]
        return {"inline_keyboard": rows}

    def _country_inline_keyboard(self, continent: str, selected: list[str]) -> dict[str, object]:
        countries = CONTINENT_COUNTRIES.get(continent, [])
        rows: list[list[dict[str, str]]] = []
        row: list[dict[str, str]] = []
        for country in countries:
            label = f"{SELECTED_PREFIX}{country}" if country in selected else country
            row.append(self._inline_button(label, self._region_callback("toggle", continent, country)))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append(
            [
                self._inline_button(CANCEL_LABEL, self._region_callback("cancel")),
                self._inline_button(BACK_LABEL, self._region_callback("back")),
                self._inline_button(CONFIRM_LABEL, self._region_callback("confirm")),
            ]
        )
        return {"inline_keyboard": rows}

    def _country_prompt_text(self, continent: str, selected: list[str]) -> str:
        selected_text = ", ".join(selected) if selected else "none yet"
        return (
            f"<b>{html.escape(continent)}</b>\n"
            "Tap countries or regions to toggle them, then press Confirm ✅.\n"
            f"\n<b>Selected</b>\n{html.escape(selected_text)}"
        )

    def _match_choice(self, raw_text: str, options: list[str] | tuple[str, ...] | object) -> str | None:
        for option in options:
            if raw_text.casefold() == str(option).casefold():
                return str(option)
        return None

    def _toggle_selection(self, selected: list[str], country: str) -> list[str]:
        if country in selected:
            return [item for item in selected if item != country]
        return [*selected, country]

    def _inline_button(self, text: str, callback_data: str) -> dict[str, str]:
        return {"text": text, "callback_data": callback_data}

    def _subscribe_mode_keyboard(self) -> dict[str, object]:
        return {
            "inline_keyboard": [
                [
                    self._inline_button(SUBSCRIBE_ALL_OPTION_LABEL, self._subscribe_callback("all")),
                    self._inline_button(SUBSCRIBE_REGION_OPTION_LABEL, self._subscribe_callback("region")),
                ],
                [self._inline_button(CANCEL_LABEL, self._subscribe_callback("cancel"))],
            ]
        }

    def _subscribe_callback(self, action: str) -> str:
        return f"subscribe|{action}"

    def _parse_subscribe_callback(self, callback_data: str) -> str:
        parts = callback_data.split("|", 2)
        return parts[1] if len(parts) > 1 else ""

    def _region_callback(self, action: str, *parts: str) -> str:
        filtered_parts = [part for part in parts if part]
        return "|".join(["region", action, *filtered_parts])

    def _parse_region_callback(self, callback_data: str) -> tuple[str, str, str]:
        parts = callback_data.split("|", 3)
        action = parts[1] if len(parts) > 1 else ""
        first_arg = parts[2] if len(parts) > 2 else ""
        second_arg = parts[3] if len(parts) > 3 else ""
        return action, first_arg, second_arg

    def _answer_callback(self, update: TelegramUpdate, text: str | None = None) -> None:
        if not update.callback_query_id:
            return
        try:
            self.telegram_client.answer_callback_query(update.callback_query_id, text)
        except Exception:
            logger.exception("Failed to answer callback query %s.", update.callback_query_id)



    def _encode_region_filters(self, regions: list[str]) -> str | None:
        cleaned = [region for region in regions if region]
        if not cleaned:
            return None
        if len(cleaned) == 1:
            return cleaned[0]
        return json.dumps(cleaned, separators=(",", ":"))

    def _decode_region_filters(self, region_filter: str | None) -> list[str]:
        if not region_filter:
            return []
        stripped = region_filter.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return [region_filter]
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item).strip()]
        if "," in stripped:
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return [region_filter]

    def _format_region_scope(self, region_filter: str | None) -> str:
        regions = self._decode_region_filters(region_filter)
        if not regions:
            return "global"
        return ", ".join(regions)

    def _quick_actions_keyboard(self) -> dict[str, object]:
        return {
            "keyboard": [
                [{"text": SUBSCRIBE_LABEL}, {"text": STATUS_LABEL}],
                [{"text": LATEST_SUBSCRIBED_LABEL}, {"text": LATEST_LABEL}],
                [{"text": UNSUBSCRIBE_LABEL}, {"text": TIMEZONE_LABEL}],
            ],
            "resize_keyboard": True,
            "is_persistent": True,
            "input_field_placeholder": "Tap a command or type your own...",
        }

    def _normalize_quick_action(self, text: str) -> str:
        quick_actions = {
            SUBSCRIBE_LABEL.casefold(): "/subscribe",
            "subscribe to all".casefold(): "/subscribe_all",
            "subscribe by region".casefold(): "/region",
            LATEST_LABEL.casefold(): "/latest",
            "latest".casefold(): "/latest",
            LATEST_SUBSCRIBED_LABEL.casefold(): "/latest_subscribed",
            STATUS_LABEL.casefold(): "/status",
            UNSUBSCRIBE_LABEL.casefold(): "/unsubscribe",
            TIMEZONE_LABEL.casefold(): "/timezone",
            "timezone": "/timezone",
        }
        return quick_actions.get(text.casefold(), text)

    def _get_chat_timezone(self, chat_id: int):
        timezone_name = self._get_chat_timezone_name(chat_id)
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            return timezone.utc

    def _get_chat_timezone_name(self, chat_id: int) -> str:
        return self._get_stored_chat_timezone_name(chat_id) or "UTC"

    def _get_stored_chat_timezone_name(self, chat_id: int) -> str | None:
        with self._timezone_cache_lock:
            if chat_id in self._chat_timezones:
                return self._chat_timezones[chat_id]

        timezone_name = self.storage.get_chat_timezone(chat_id)
        with self._timezone_cache_lock:
            self._chat_timezones[chat_id] = timezone_name
        return timezone_name

    def _set_chat_timezone_name(self, chat_id: int, timezone_name: str) -> None:
        self.storage.set_chat_timezone(chat_id, timezone_name)
        with self._timezone_cache_lock:
            self._chat_timezones[chat_id] = timezone_name

    def _get_region_picker_selection(self, chat_id: int) -> list[str]:
        subscription = self.storage.get_subscription(chat_id)
        if not subscription or not subscription.enabled:
            return []
        return self._decode_region_filters(subscription.region_filter)


