from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earthquake_bot.config import Config
from earthquake_bot.models import EarthquakeEvent, Subscription
from earthquake_bot.service import CONTINENT_COUNTRIES, EarthquakeBotService
from earthquake_bot.storage import Storage
from earthquake_bot.telegram_api import TelegramUpdate
from earthquake_bot.timezone_catalog import get_country
from earthquake_bot.usgs import USGSClient


class StubTelegramClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.edits: list[dict[str, Any]] = []
        self.callback_answers: list[dict[str, Any]] = []

    def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        self.messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
            }
        )

    def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        self.edits.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
            }
        )

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None:
        self.callback_answers.append({"callback_query_id": callback_query_id, "text": text})


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "bot.sqlite3"
        self.admin_chat_id = 777
        self.config = Config(
            telegram_bot_token="test-token",
            usgs_feed_url="https://example.com/feed",
            usgs_poll_seconds=60,
            default_min_magnitude=5.0,
            database_path=database_path,
            telegram_long_poll_seconds=10,
            admin_chat_ids=frozenset({self.admin_chat_id}),
        )
        self.storage = Storage(database_path)
        self.telegram = StubTelegramClient()
        self.service = EarthquakeBotService(
            self.config,
            self.storage,
            USGSClient(self.config.usgs_feed_url),
            self.telegram,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_parse_subscription_args_defaults(self) -> None:
        min_magnitude, region_filter = self.service._parse_subscription_args("")
        self.assertEqual(min_magnitude, 5.0)
        self.assertIsNone(region_filter)

    def test_parse_subscription_args_with_magnitude_and_region(self) -> None:
        min_magnitude, region_filter = self.service._parse_subscription_args("4.5 Japan")
        self.assertEqual(min_magnitude, 4.5)
        self.assertEqual(region_filter, "Japan")

    def test_parse_subscription_args_with_region_only(self) -> None:
        min_magnitude, region_filter = self.service._parse_subscription_args("Indonesia")
        self.assertEqual(min_magnitude, 5.0)
        self.assertEqual(region_filter, "Indonesia")

    def test_normalize_subscribe_command_with_alias_magnitude_and_region(self) -> None:
        command, args = self.service._normalize_subscribe_command("/subscribe_4_5_japan")
        self.assertEqual(command, "/subscribe")
        self.assertEqual(args, "4.5 japan")

    def test_normalize_subscribe_command_with_alias_region_only(self) -> None:
        command, args = self.service._normalize_subscribe_command("/subscribe_indonesia")
        self.assertEqual(command, "/subscribe")
        self.assertEqual(args, "indonesia")

    def test_normalize_quick_action_maps_plain_button_labels(self) -> None:
        self.assertEqual(self.service._normalize_quick_action("Subscribe"), "/subscribe")
        self.assertEqual(self.service._normalize_quick_action("Subscribe to all"), "/subscribe_all")
        self.assertEqual(self.service._normalize_quick_action("Subscribe by region"), "/region")
        self.assertEqual(self.service._normalize_quick_action("Latest, all"), "/latest")
        self.assertEqual(self.service._normalize_quick_action("Latest"), "/latest")
        self.assertEqual(self.service._normalize_quick_action("Latest subscribed"), "/latest_subscribed")
        self.assertEqual(self.service._normalize_quick_action("Edit Timezone"), "/timezone")
        self.assertEqual(self.service._normalize_quick_action("Timezone"), "/timezone")

    def test_chat_timezone_lookup_uses_cache_after_first_read(self) -> None:
        self.storage.set_chat_timezone(99, "Asia/Singapore")

        self.assertTrue(self.service._has_chat_timezone(99))

        def fail_timezone_lookup(_: int) -> str | None:
            raise AssertionError("timezone cache was not used")

        self.storage.get_chat_timezone = fail_timezone_lookup  # type: ignore[method-assign]

        self.assertTrue(self.service._has_chat_timezone(99))
        self.assertEqual(self.service._get_chat_timezone_name(99), "Asia/Singapore")

    def test_edit_inline_message_skips_cached_noop_without_second_telegram_edit(self) -> None:
        markup = {"inline_keyboard": [[{"text": "Confirm", "callback_data": "ok"}]]}

        self.service._edit_inline_message(99, 123, "<b>Region Alerts</b>", markup)
        self.service._edit_inline_message(99, 123, "<b>Region Alerts</b>", markup)

        self.assertEqual(len(self.telegram.edits), 1)

    def test_event_matches_region_filter_case_insensitive(self) -> None:
        event = EarthquakeEvent(
            event_id="evt-1",
            updated_ms=1,
            magnitude=6.0,
            place="120 km SE of Hokkaido, Japan",
            event_time=datetime.now(timezone.utc),
            detail_url="https://example.com/detail",
            event_url="https://example.com/event",
            latitude=1.0,
            longitude=1.0,
            depth_km=10.0,
            tsunami=False,
            status="reviewed",
            significance=800,
            felt_reports=10,
            alert_level=None,
            review_status="reviewed",
            shakemap_url=None,
            max_mmi=None,
        )
        subscription = Subscription(
            chat_id=123,
            min_magnitude=5.5,
            region_filter="japan",
            enabled=True,
            updated_at=datetime.now(timezone.utc),
        )
        self.assertTrue(self.service._event_matches_subscription(event, subscription))

    def test_event_matches_any_multi_region_filter(self) -> None:
        event = EarthquakeEvent(
            event_id="evt-3",
            updated_ms=1,
            magnitude=6.1,
            place="87 km ESE of Miyazaki, Japan",
            event_time=datetime.now(timezone.utc),
            detail_url="https://example.com/detail",
            event_url="https://example.com/event",
            latitude=1.0,
            longitude=1.0,
            depth_km=20.0,
            tsunami=False,
            status="reviewed",
            significance=700,
            felt_reports=5,
            alert_level=None,
            review_status="reviewed",
            shakemap_url=None,
            max_mmi=None,
        )
        multi_filter = self.service._encode_region_filters(["Indonesia", "Japan"])
        subscription = Subscription(
            chat_id=123,
            min_magnitude=5.5,
            region_filter=multi_filter,
            enabled=True,
            updated_at=datetime.now(timezone.utc),
        )
        self.assertTrue(self.service._event_matches_subscription(event, subscription))

    def test_should_not_send_minor_update_alert(self) -> None:
        previous_event = EarthquakeEvent(
            event_id="evt-update",
            updated_ms=10,
            magnitude=5.2,
            place="101 km E of Bitung, Indonesia",
            event_time=datetime.now(timezone.utc),
            detail_url="https://example.com/detail",
            event_url="https://example.com/event",
            latitude=1.0,
            longitude=126.0,
            depth_km=35.0,
            tsunami=False,
            status="reviewed",
            significance=416,
            felt_reports=3,
            alert_level=None,
            review_status="reviewed",
            shakemap_url=None,
            max_mmi=None,
        )
        updated_event = EarthquakeEvent(
            event_id="evt-update",
            updated_ms=11,
            magnitude=5.3,
            place="101 km E of Bitung, Indonesia",
            event_time=previous_event.event_time,
            detail_url=previous_event.detail_url,
            event_url=previous_event.event_url,
            latitude=previous_event.latitude,
            longitude=previous_event.longitude,
            depth_km=36.0,
            tsunami=False,
            status="reviewed",
            significance=420,
            felt_reports=3,
            alert_level=None,
            review_status="reviewed",
            shakemap_url=None,
            max_mmi=None,
        )

        self.assertFalse(self.service._should_send_update_alert(previous_event, updated_event))

    def test_should_send_update_alert_for_new_tsunami_flag(self) -> None:
        previous_event = EarthquakeEvent(
            event_id="evt-tsunami",
            updated_ms=20,
            magnitude=6.0,
            place="88 km E of Sendai, Japan",
            event_time=datetime.now(timezone.utc),
            detail_url="https://example.com/detail",
            event_url="https://example.com/event",
            latitude=38.0,
            longitude=142.0,
            depth_km=20.0,
            tsunami=False,
            status="reviewed",
            significance=700,
            felt_reports=8,
            alert_level=None,
            review_status="reviewed",
            shakemap_url=None,
            max_mmi=None,
        )
        updated_event = EarthquakeEvent(
            event_id="evt-tsunami",
            updated_ms=21,
            magnitude=6.1,
            place="88 km E of Sendai, Japan",
            event_time=previous_event.event_time,
            detail_url=previous_event.detail_url,
            event_url=previous_event.event_url,
            latitude=previous_event.latitude,
            longitude=previous_event.longitude,
            depth_km=previous_event.depth_km,
            tsunami=True,
            status="reviewed",
            significance=710,
            felt_reports=8,
            alert_level=None,
            review_status="reviewed",
            shakemap_url=None,
            max_mmi=None,
        )

        self.assertTrue(self.service._should_send_update_alert(previous_event, updated_event))

    def test_decode_region_filters_supports_legacy_comma_strings(self) -> None:
        decoded = self.service._decode_region_filters("Japan,Indonesia")

        self.assertEqual(decoded, ["Japan", "Indonesia"])

    def test_latest_text_uses_chat_timezone(self) -> None:
        self.storage.set_chat_timezone(99, "Asia/Singapore")
        event = EarthquakeEvent(
            event_id="evt-2",
            updated_ms=2,
            magnitude=2.0,
            place="15 km SW of Hawi, Hawaii",
            event_time=datetime(2026, 3, 29, 12, 48, 21, tzinfo=timezone.utc),
            detail_url="https://example.com/detail",
            event_url="https://example.com/event",
            latitude=1.0,
            longitude=1.0,
            depth_km=8.0,
            tsunami=False,
            status="reviewed",
            significance=120,
            felt_reports=1,
            alert_level=None,
            review_status="reviewed",
            shakemap_url=None,
            max_mmi=None,
        )
        self.storage.upsert_event(event)
        message = self.service._latest_text(99)
        self.assertIn("<code>M2.0  03-29 20:48 +08</code>", message)
        self.assertIn("Latest, all", message)
        self.assertIn("15 km SW of Hawi, Hawaii", message)

    def test_latest_subscribed_text_groups_regions_and_ignores_magnitude_threshold(self) -> None:
        self.storage.set_chat_timezone(99, "Asia/Singapore")
        self.storage.upsert_subscription(99, 5.0, self.service._encode_region_filters(["Japan", "Indonesia"]))
        japan_event = EarthquakeEvent(
            event_id="evt-jp",
            updated_ms=2,
            magnitude=4.4,
            place="81 km SE of Taira, Japan",
            event_time=datetime(2026, 3, 29, 12, 48, 21, tzinfo=timezone.utc),
            detail_url="https://example.com/detail/jp",
            event_url="https://example.com/event/jp",
            latitude=36.1,
            longitude=141.2,
            depth_km=10.0,
            tsunami=False,
            status="reviewed",
            significance=400,
            felt_reports=1,
            alert_level=None,
            review_status="reviewed",
            shakemap_url=None,
            max_mmi=None,
        )
        indonesia_event = EarthquakeEvent(
            event_id="evt-id",
            updated_ms=3,
            magnitude=4.2,
            place="44 km S of Banda Aceh, Indonesia",
            event_time=datetime(2026, 3, 29, 13, 15, 0, tzinfo=timezone.utc),
            detail_url="https://example.com/detail/id",
            event_url="https://example.com/event/id",
            latitude=5.4,
            longitude=95.2,
            depth_km=12.0,
            tsunami=False,
            status="reviewed",
            significance=320,
            felt_reports=1,
            alert_level=None,
            review_status="reviewed",
            shakemap_url=None,
            max_mmi=None,
        )
        self.storage.upsert_event(japan_event)
        self.storage.upsert_event(indonesia_event)
        for index in range(305):
            self.storage.upsert_event(
                EarthquakeEvent(
                    event_id=f"evt-ak-{index}",
                    updated_ms=1000 + index,
                    magnitude=5.6,
                    place=f"{index} km SW of Anchorage, Alaska",
                    event_time=datetime(2026, 3, 30, 0, 0, tzinfo=timezone.utc).replace(minute=index % 60, second=index % 60),
                    detail_url=f"https://example.com/detail/ak/{index}",
                    event_url=f"https://example.com/event/ak/{index}",
                    latitude=61.1,
                    longitude=-150.1,
                    depth_km=15.0,
                    tsunami=False,
                    status="reviewed",
                    significance=500,
                    felt_reports=2,
                    alert_level=None,
                    review_status="reviewed",
                    shakemap_url=None,
                    max_mmi=None,
                )
            )

        message = self.service._latest_subscribed_text(99)

        self.assertIn("Latest subscribed", message)
        self.assertIn("=================================", message)
        self.assertIn("<b>🇯🇵 Japan</b>", message)
        self.assertIn("<b>🇮🇩 Indonesia</b>", message)
        self.assertIn("81 km SE of Taira, Japan", message)
        self.assertIn("44 km S of Banda Aceh, Indonesia", message)
        self.assertNotIn("Anchorage, Alaska", message)

    def test_latest_subscribed_without_active_subscription_prompts_subscribe(self) -> None:
        self.storage.set_chat_timezone(99, "Asia/Singapore")

        message = self.service._latest_subscribed_text(99)

        self.assertIn("Latest subscribed", message)
        self.assertIn("Tap <b>Subscribe</b> first.", message)

    def test_timezone_command_updates_chat_timezone(self) -> None:
        self.service.handle_update(
            TelegramUpdate(update_id=1, chat_id=99, text="/timezone Asia/Singapore", first_name="Darren")
        )
        self.assertEqual(self.storage.get_chat_timezone(99), "Asia/Singapore")
        self.assertIn("Timezone Updated", self.telegram.messages[0]["text"])

    def test_first_manual_timezone_command_sends_welcome_after_update(self) -> None:
        self.service.handle_update(
            TelegramUpdate(update_id=1, chat_id=99, text="/timezone Asia/Singapore", first_name="Darren")
        )
        self.assertEqual(self.storage.get_chat_timezone(99), "Asia/Singapore")
        self.assertEqual(len(self.telegram.messages), 2)
        self.assertIn("Timezone Updated", self.telegram.messages[0]["text"])
        self.assertIn("Earthquake Monitor", self.telegram.messages[1]["text"])

    def test_start_without_timezone_prompts_picker(self) -> None:
        self.service.handle_update(TelegramUpdate(update_id=1, chat_id=99, text="/start", first_name="Darren"))
        self.assertIn("Set your timezone first", self.telegram.messages[-1]["text"])
        self.assertIn("inline_keyboard", self.telegram.messages[-1]["reply_markup"])

    def test_subscribe_without_args_opens_mode_picker(self) -> None:
        self.storage.set_chat_timezone(99, "Asia/Singapore")

        self.service.handle_update(TelegramUpdate(update_id=1, chat_id=99, text="/subscribe", first_name="Darren"))

        self.assertIn("<b>Subscribe</b>", self.telegram.messages[-1]["text"])
        keyboard = self.telegram.messages[-1]["reply_markup"]["inline_keyboard"]
        self.assertEqual(keyboard[0][0]["text"], "To all")
        self.assertEqual(keyboard[0][1]["text"], "By region")

    def test_latest_without_timezone_redirects_to_timezone_setup(self) -> None:
        self.service.handle_update(TelegramUpdate(update_id=1, chat_id=99, text="/latest", first_name="Darren"))
        self.assertIn("Timezone Required", self.telegram.messages[-1]["text"])
        self.assertIn("inline_keyboard", self.telegram.messages[-1]["reply_markup"])

    def test_timezone_command_without_args_opens_region_picker(self) -> None:
        self.storage.set_chat_timezone(99, "Asia/Singapore")
        self.service.handle_update(TelegramUpdate(update_id=1, chat_id=99, text="/timezone", first_name="Darren"))
        self.assertIn("Pick a region", self.telegram.messages[-1]["text"])
        self.assertIn("inline_keyboard", self.telegram.messages[-1]["reply_markup"])

    def test_required_timezone_picker_hides_cancel(self) -> None:
        self.service.handle_update(TelegramUpdate(update_id=1, chat_id=99, text="/start", first_name="Darren"))
        keyboard = self.telegram.messages[-1]["reply_markup"]["inline_keyboard"]
        labels = [button["text"] for row in keyboard for button in row]
        self.assertNotIn("Cancel", labels)

    def test_timezone_callback_country_pick_saves_timezone(self) -> None:
        self.service.handle_update(TelegramUpdate(update_id=1, chat_id=99, text="/start", first_name="Darren"))
        self.service.handle_update(
            TelegramUpdate(
                update_id=2,
                chat_id=99,
                text="",
                first_name="Darren",
                message_id=400,
                callback_query_id="tz-1",
                callback_data="timezone|region|asia|0",
            )
        )

        keyboard = self.telegram.edits[-1]["reply_markup"]["inline_keyboard"]
        country_callback = None
        for row in keyboard:
            button = row[0]
            if button["callback_data"].startswith("timezone|country|"):
                country_callback = button["callback_data"]
                break

        self.assertIsNotNone(country_callback)
        country_code = str(country_callback).split("|")[2]
        expected_country = get_country(country_code)
        self.assertIsNotNone(expected_country)
        self.service.handle_update(
            TelegramUpdate(
                update_id=3,
                chat_id=99,
                text="",
                first_name="Darren",
                message_id=400,
                callback_query_id="tz-2",
                callback_data=str(country_callback),
            )
        )

        self.assertEqual(self.storage.get_chat_timezone(99), expected_country.timezones[0])
        self.assertIn("Timezone Updated", self.telegram.edits[-1]["text"])
        self.assertIn("Earthquake Monitor", self.telegram.messages[-1]["text"])

    def test_multi_timezone_country_preserves_country_page_in_back_button(self) -> None:
        self.storage.set_chat_timezone(99, "Asia/Singapore")
        self.service.handle_update(TelegramUpdate(update_id=1, chat_id=99, text="/timezone", first_name="Darren"))
        self.service.handle_update(
            TelegramUpdate(
                update_id=2,
                chat_id=99,
                text="",
                first_name="Darren",
                message_id=401,
                callback_query_id="tz-3",
                callback_data="timezone|country|BR|americas|1",
            )
        )

        footer = self.telegram.edits[-1]["reply_markup"]["inline_keyboard"][-1]
        self.assertEqual(footer[0]["callback_data"], "timezone|region|americas|1")

    def test_region_context_clears_when_switching_to_other_command(self) -> None:
        self.storage.set_chat_timezone(99, "Asia/Singapore")
        self.service.handle_update(TelegramUpdate(update_id=1, chat_id=99, text="/region", first_name="Darren"))
        self.assertIsNotNone(self.service._get_region_picker_context(99))

        self.service.handle_update(TelegramUpdate(update_id=2, chat_id=99, text="/status", first_name="Darren"))
        self.assertIsNone(self.service._get_region_picker_context(99))

    def test_status_text_mentions_admin_tools_for_admin_chat(self) -> None:
        self.storage.set_chat_timezone(self.admin_chat_id, "Asia/Singapore")

        status = self.service._status_text(self.admin_chat_id)

        self.assertIn("Admin tools", status)

    def test_status_reply_markup_uses_admin_inline_tools_for_admin_chat(self) -> None:
        reply_markup = self.service._status_reply_markup(self.admin_chat_id)

        self.assertIn("inline_keyboard", reply_markup)
        labels = [button["text"] for row in reply_markup["inline_keyboard"] for button in row]
        self.assertEqual(labels, ["Send demo alert", "Health snapshot"])

    def test_format_event_message_uses_major_title_and_tsunami_note(self) -> None:
        event = EarthquakeEvent(
            event_id="evt-major",
            updated_ms=3,
            magnitude=6.8,
            place="88 km E of Sendai, Japan",
            event_time=datetime(2026, 3, 29, 12, 0, tzinfo=timezone.utc),
            detail_url="https://example.com/detail",
            event_url="https://example.com/event",
            latitude=1.0,
            longitude=1.0,
            depth_km=18.0,
            tsunami=True,
            status="reviewed",
            significance=900,
            felt_reports=30,
            alert_level=None,
            review_status="reviewed",
            shakemap_url="https://example.com/shakemap",
            max_mmi=6.4,
        )

        message = self.service._format_event_message(99, event, is_update=False)

        self.assertIn("🚨 <b>MAJOR QUAKE ALERT</b>", message)
        self.assertIn("<i><b>POTENTIALLY DAMAGING QUAKE. EXPECT AFTERSHOCKS AND MONITOR OFFICIAL UPDATES.</b></i>", message)
        self.assertIn("<i><b>TSUNAMI NOTE: CHECK OFFICIAL COASTAL ADVISORIES NOW.</b></i>", message)
        self.assertIn("Official source:", message)
        self.assertIn("ShakeMap", message)

    def test_format_event_message_uses_red_alert_wording(self) -> None:
        event = EarthquakeEvent(
            event_id="evt-red",
            updated_ms=4,
            magnitude=7.2,
            place="120 km S of Kodiak, Alaska",
            event_time=datetime(2026, 3, 29, 13, 0, tzinfo=timezone.utc),
            detail_url="https://example.com/detail",
            event_url="https://example.com/event",
            latitude=1.0,
            longitude=1.0,
            depth_km=25.0,
            tsunami=False,
            status="reviewed",
            significance=950,
            felt_reports=40,
            alert_level="red",
            review_status="reviewed",
            shakemap_url=None,
            max_mmi=7.1,
        )

        message = self.service._format_event_message(99, event, is_update=False)

        self.assertIn("🚨 <b>RED ALERT MAJOR QUAKE</b>", message)
        self.assertIn("<i><b>HIGHEST IMPACT RISK. PRIORITIZE OFFICIAL EMERGENCY GUIDANCE.</b></i>", message)
        self.assertIn("RED | highest impact risk", message)

    def test_format_event_message_uses_strong_title_for_magnitude_five(self) -> None:
        event = EarthquakeEvent(
            event_id="evt-strong",
            updated_ms=5,
            magnitude=5.1,
            place="81 km SE of Taira, Japan",
            event_time=datetime(2026, 3, 30, 1, 12, tzinfo=timezone.utc),
            detail_url="https://example.com/detail",
            event_url="https://example.com/event",
            latitude=1.0,
            longitude=1.0,
            depth_km=10.0,
            tsunami=False,
            status="reviewed",
            significance=400,
            felt_reports=12,
            alert_level=None,
            review_status="reviewed",
            shakemap_url=None,
            max_mmi=None,
        )

        message = self.service._format_event_message(99, event, is_update=False)

        self.assertIn("🚨 <b>STRONG QUAKE ALERT</b>", message)
        self.assertIn("<i><b>STAY ALERT FOR LOCAL UPDATES AND AFTERSHOCKS.</b></i>", message)
        self.assertIn("<b>81 km SE of Taira, Japan</b>", message)

    def test_notify_matching_subscribers_enqueues_alerts(self) -> None:
        self.storage.set_chat_timezone(99, "Asia/Singapore")
        subscription = Subscription(
            chat_id=99,
            min_magnitude=5.0,
            region_filter="Japan",
            enabled=True,
            updated_at=datetime.now(timezone.utc),
        )
        event = EarthquakeEvent(
            event_id="evt-queue",
            updated_ms=9,
            magnitude=5.4,
            place="81 km SE of Taira, Japan",
            event_time=datetime(2026, 3, 30, 1, 12, tzinfo=timezone.utc),
            detail_url="https://example.com/detail",
            event_url="https://example.com/event",
            latitude=1.0,
            longitude=1.0,
            depth_km=10.0,
            tsunami=False,
            status="reviewed",
            significance=400,
            felt_reports=12,
            alert_level=None,
            review_status="reviewed",
            shakemap_url=None,
            max_mmi=None,
        )

        self.service._notify_matching_subscribers(event, [subscription], is_update=False)

        self.assertEqual(self.telegram.messages, [])
        jobs = self.storage.claim_outbound_messages(limit=5, lease_seconds=60)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].chat_id, 99)
        self.assertEqual(jobs[0].message_kind, "photo")
        self.assertTrue(jobs[0].media is not None and len(jobs[0].media) > 0)
        self.assertIn("Official source:", jobs[0].text)

    def test_notify_matching_subscribers_keeps_text_for_smaller_quakes(self) -> None:
        self.storage.set_chat_timezone(99, "Asia/Singapore")
        subscription = Subscription(
            chat_id=99,
            min_magnitude=4.0,
            region_filter="Japan",
            enabled=True,
            updated_at=datetime.now(timezone.utc),
        )
        event = EarthquakeEvent(
            event_id="evt-text",
            updated_ms=10,
            magnitude=4.6,
            place="20 km E of Chiba, Japan",
            event_time=datetime(2026, 3, 30, 3, 0, tzinfo=timezone.utc),
            detail_url="https://example.com/detail",
            event_url="https://example.com/event",
            latitude=35.6,
            longitude=140.2,
            depth_km=24.0,
            tsunami=False,
            status="reviewed",
            significance=300,
            felt_reports=5,
            alert_level=None,
            review_status="reviewed",
            shakemap_url=None,
            max_mmi=None,
        )

        self.service._notify_matching_subscribers(event, [subscription], is_update=False)

        jobs = self.storage.claim_outbound_messages(limit=5, lease_seconds=60)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].message_kind, "text")
        self.assertIn("EARTHQUAKE ALERT", jobs[0].text)

    def test_region_command_starts_continent_selection(self) -> None:
        self.storage.set_chat_timezone(99, "Asia/Singapore")
        self.service.handle_update(TelegramUpdate(update_id=1, chat_id=99, text="/region", first_name="Darren"))
        context = self.service._get_region_picker_context(99)
        self.assertIsNotNone(context)
        self.assertEqual(context["step"], "choose_continent")
        self.assertIn("Region Alerts", self.telegram.messages[-1]["text"])
        self.assertIn("inline_keyboard", self.telegram.messages[-1]["reply_markup"])
        self.assertIsNone(self.storage.get_chat_context(99))

    def test_region_command_preserves_existing_subscription_selection(self) -> None:
        self.storage.set_chat_timezone(99, "Asia/Singapore")
        self.storage.upsert_subscription(99, 5.0, "Japan")

        self.service.handle_update(TelegramUpdate(update_id=1, chat_id=99, text="/region", first_name="Darren"))
        self.service.handle_update(TelegramUpdate(update_id=2, chat_id=99, text="Asia", first_name="Darren"))

        context = self.service._get_region_picker_context(99)
        self.assertIsNotNone(context)
        self.assertEqual(context["step"], "choose_country")
        self.assertEqual(context["value"]["selected"], ["Japan"])
        self.assertIn("Japan", self.telegram.messages[-1]["text"])

    def test_region_flow_continent_then_country_creates_subscription(self) -> None:
        self.storage.set_chat_timezone(99, "Asia/Singapore")
        self.service._set_region_picker_context(99, "choose_continent")
        self.service.handle_update(TelegramUpdate(update_id=1, chat_id=99, text="Asia", first_name="Darren"))
        context = self.service._get_region_picker_context(99)
        self.assertIsNotNone(context)
        self.assertEqual(context["step"], "choose_country")
        self.assertEqual(context["value"]["continent"], "Asia")
        self.assertEqual(context["value"]["selected"], [])

        self.service.handle_update(TelegramUpdate(update_id=2, chat_id=99, text="Japan", first_name="Darren"))
        context = self.service._get_region_picker_context(99)
        self.assertIsNotNone(context)
        self.assertEqual(context["value"]["selected"], ["Japan"])

        self.service.handle_update(TelegramUpdate(update_id=3, chat_id=99, text="Indonesia", first_name="Darren"))
        context = self.service._get_region_picker_context(99)
        self.assertIsNotNone(context)
        self.assertEqual(context["value"]["selected"], ["Japan", "Indonesia"])

        self.service.handle_update(TelegramUpdate(update_id=4, chat_id=99, text="Confirm", first_name="Darren"))
        subscription = self.storage.get_subscription(99)
        self.assertIsNotNone(subscription)
        self.assertEqual(self.service._decode_region_filters(subscription.region_filter), ["Japan", "Indonesia"])
        self.assertIsNone(self.service._get_region_picker_context(99))

    def test_region_callback_flow_edits_single_message_until_confirm(self) -> None:
        self.storage.set_chat_timezone(99, "Asia/Singapore")
        self.service.handle_update(TelegramUpdate(update_id=1, chat_id=99, text="/region", first_name="Darren"))

        self.service.handle_update(
            TelegramUpdate(
                update_id=2,
                chat_id=99,
                text="",
                first_name="Darren",
                message_id=321,
                callback_query_id="cb-1",
                callback_data="region|continent|Asia",
            )
        )
        self.service.handle_update(
            TelegramUpdate(
                update_id=3,
                chat_id=99,
                text="",
                first_name="Darren",
                message_id=321,
                callback_query_id="cb-2",
                callback_data="region|toggle|Asia|Japan",
            )
        )
        self.service.handle_update(
            TelegramUpdate(
                update_id=4,
                chat_id=99,
                text="",
                first_name="Darren",
                message_id=321,
                callback_query_id="cb-3",
                callback_data="region|toggle|Asia|Philippines",
            )
        )
        self.service.handle_update(
            TelegramUpdate(
                update_id=5,
                chat_id=99,
                text="",
                first_name="Darren",
                message_id=321,
                callback_query_id="cb-4",
                callback_data="region|confirm",
            )
        )

        subscription = self.storage.get_subscription(99)
        self.assertIsNotNone(subscription)
        self.assertEqual(self.service._decode_region_filters(subscription.region_filter), ["Japan", "Philippines"])
        self.assertEqual(len(self.telegram.messages), 1)
        self.assertGreaterEqual(len(self.telegram.edits), 4)
        self.assertIn("Alerts On", self.telegram.edits[-1]["text"])
        self.assertEqual(self.telegram.edits[-1]["reply_markup"], {"inline_keyboard": []})
        self.assertEqual(len(self.telegram.callback_answers), 4)

    def test_subscribe_region_callback_preserves_existing_region_selection(self) -> None:
        self.storage.set_chat_timezone(99, "Asia/Singapore")
        self.storage.upsert_subscription(99, 5.0, "Japan")

        self.service.handle_update(
            TelegramUpdate(
                update_id=1,
                chat_id=99,
                text="",
                first_name="Darren",
                message_id=500,
                callback_query_id="sub-1",
                callback_data="subscribe|region",
            )
        )
        self.service.handle_update(
            TelegramUpdate(
                update_id=2,
                chat_id=99,
                text="",
                first_name="Darren",
                message_id=500,
                callback_query_id="sub-2",
                callback_data="region|continent|Asia",
            )
        )

        context = self.service._get_region_picker_context(99)
        self.assertIsNotNone(context)
        self.assertEqual(context["value"]["selected"], ["Japan"])
        self.assertIn("Japan", self.telegram.edits[-1]["text"])

    def test_admin_test_callback_queues_alert(self) -> None:
        self.storage.set_chat_timezone(self.admin_chat_id, "Asia/Singapore")

        self.service.handle_update(
            TelegramUpdate(
                update_id=1,
                chat_id=self.admin_chat_id,
                text="",
                first_name="Darren",
                message_id=654,
                callback_query_id="admin-1",
                callback_data="admin|test",
            )
        )

        self.assertIn("Queued", self.telegram.callback_answers[-1]["text"])
        self.assertIn("Demo Alert Queued", self.telegram.messages[-1]["text"])
        jobs = self.storage.claim_outbound_messages(limit=5, lease_seconds=60)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].chat_id, self.admin_chat_id)
        self.assertIn("Demo only.", jobs[0].text)

    def test_admin_health_callback_sends_health_snapshot(self) -> None:
        self.storage.set_chat_timezone(self.admin_chat_id, "Asia/Singapore")

        self.service.handle_update(
            TelegramUpdate(
                update_id=1,
                chat_id=self.admin_chat_id,
                text="",
                first_name="Darren",
                message_id=655,
                callback_query_id="admin-2",
                callback_data="admin|health",
            )
        )

        self.assertIn("Health sent.", self.telegram.callback_answers[-1]["text"])
        self.assertIn("Health Snapshot", self.telegram.messages[-1]["text"])

    def test_admin_status_keyboard_has_two_admin_buttons(self) -> None:
        keyboard = self.service._admin_status_keyboard()

        labels = [button["text"] for row in keyboard["inline_keyboard"] for button in row]
        self.assertEqual(labels, ["Send demo alert", "Health snapshot"])

    def test_broadcast_admin_message_queues_one_per_active_chat(self) -> None:
        self.storage.upsert_subscription(101, 5.0, "Japan")
        self.storage.upsert_subscription(202, 5.0, "Indonesia")
        self.storage.upsert_subscription(202, 5.0, "Indonesia")

        result = self.service._broadcast_admin_message("Service maintenance tonight")

        self.assertIn("Broadcast Queued", result)
        self.assertIn("2", result)
        jobs = self.storage.claim_outbound_messages(limit=5, lease_seconds=60)
        self.assertEqual(len(jobs), 2)
        self.assertTrue(all(job.category == "admin_broadcast" for job in jobs))
        self.assertTrue(all("Earthquake Monitor Broadcast" in job.text for job in jobs))

    def test_broadcast_requires_message_text(self) -> None:
        result = self.service._broadcast_admin_message("")

        self.assertIn("/broadcast your message here", result)

    def test_quick_actions_keyboard_uses_plain_labels(self) -> None:
        keyboard = self.service._quick_actions_keyboard()
        first_row = keyboard["keyboard"][0]
        second_row = keyboard["keyboard"][1]
        third_row = keyboard["keyboard"][2]
        self.assertEqual(first_row[0]["text"], "Subscribe")
        self.assertEqual(first_row[1]["text"], "Status")
        self.assertEqual(second_row[0]["text"], "Latest subscribed")
        self.assertEqual(second_row[1]["text"], "Latest, all")
        self.assertEqual(third_row[0]["text"], "Unsubscribe")
        self.assertEqual(third_row[1]["text"], "Edit Timezone")

    def test_each_continent_has_six_country_options(self) -> None:
        for countries in CONTINENT_COUNTRIES.values():
            self.assertEqual(len(countries), 6)


if __name__ == "__main__":
    unittest.main()

