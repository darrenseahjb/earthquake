from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earthquake_bot.alert_cards import AlertCardRenderer
from earthquake_bot.models import EarthquakeEvent


class AlertCardRendererTests(unittest.TestCase):
    def test_render_card_returns_png_bytes_for_japan_event(self) -> None:
        renderer = AlertCardRenderer()
        event = self._event(
            event_id="evt-card",
            place="81 km SE of Taira, Japan",
            latitude=36.1,
            longitude=141.2,
        )

        payload = renderer.render_card(
            event,
            "2026-03-30 09:12 +08",
            "Strong Quake Alert",
            ["Stay alert for local updates and aftershocks."],
        )

        self.assertTrue(payload.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(payload), 10000)

    def test_render_card_returns_png_bytes_for_monitored_regions(self) -> None:
        renderer = AlertCardRenderer()
        cases = [
            ("japan", "81 km SE of Taira, Japan", 36.1, 141.2),
            ("indonesia", "43 km S of Padang, Indonesia", -1.4, 100.3),
            ("philippines", "52 km E of Davao, Philippines", 7.2, 126.5),
            ("taiwan", "28 km E of Hualien, Taiwan", 24.0, 121.9),
            ("nepal", "19 km NE of Kathmandu, Nepal", 27.8, 85.5),
            ("turkey", "32 km E of Erzincan, Turkey", 39.8, 40.6),
            ("greece", "22 km S of Patras, Greece", 38.2, 21.7),
            ("italy", "14 km N of Naples, Italy", 40.95, 14.25),
            ("iceland", "34 km S of Hveragerdi, Iceland", 63.9, -21.0),
            ("romania", "11 km W of Focsani, Romania", 45.7, 27.0),
            ("portugal", "63 km SW of Lisbon, Portugal", 38.4, -9.7),
            ("california", "16 km WNW of Parkfield, California", 35.9, -120.6),
            ("alaska", "62 km SW of Anchorage, Alaska", 60.9, -150.8),
            ("mexico", "42 km S of Oaxaca, Mexico", 16.7, -96.7),
            ("guatemala", "28 km S of Guatemala City, Guatemala", 14.3, -90.5),
            ("costa-rica", "36 km SW of San Jose, Costa Rica", 9.7, -84.3),
            ("puerto-rico", "12 km N of Ponce, Puerto Rico", 18.4, -66.6),
            ("chile", "84 km W of Valparaiso, Chile", -33.05, -72.55),
            ("peru", "51 km SW of Lima, Peru", -12.4, -77.3),
            ("ecuador", "22 km E of Quito, Ecuador", -0.18, -78.2),
            ("colombia", "34 km NE of Bogota, Colombia", 4.9, -73.8),
            ("argentina", "27 km W of Mendoza, Argentina", -32.9, -69.1),
            ("bolivia", "41 km NW of Cochabamba, Bolivia", -17.1, -66.3),
            ("tonga", "98 km NE of Nuku'alofa, Tonga", -20.9, -174.9),
            ("new-zealand", "49 km N of Wellington, New Zealand", -41.0, 174.8),
            ("png", "71 km NE of Lae, Papua New Guinea", -6.4, 147.4),
            ("fiji", "34 km N of Suva, Fiji", -17.7, 178.5),
            ("vanuatu", "42 km NW of Port Vila, Vanuatu", -17.4, 168.0),
            ("solomon-islands", "55 km E of Honiara, Solomon Islands", -9.3, 160.4),
            ("morocco", "61 km E of Rabat, Morocco", 34.1, -5.5),
            ("algeria", "33 km S of Algiers, Algeria", 36.4, 3.2),
            ("ethiopia", "44 km NE of Addis Ababa, Ethiopia", 9.3, 39.1),
            ("tanzania", "58 km W of Dar es Salaam, Tanzania", -6.9, 38.8),
            ("uganda", "29 km SW of Kampala, Uganda", 0.1, 32.4),
            ("kenya", "44 km N of Nairobi, Kenya", -1.0, 36.9),
        ]

        for event_id, place, latitude, longitude in cases:
            with self.subTest(event_id=event_id):
                payload = renderer.render_card(
                    self._event(
                        event_id=event_id,
                        place=place,
                        latitude=latitude,
                        longitude=longitude,
                    ),
                    "2026-03-30 09:12 +08",
                    "Strong Quake Alert",
                    ["Stay alert for local updates and aftershocks."],
                )
                self.assertTrue(payload.startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertGreater(len(payload), 10000)

    def test_location_indicator_marks_offshore_epicenters(self) -> None:
        renderer = AlertCardRenderer()
        offshore_event = self._event(
            event_id="offshore",
            place="84 km W of Valparaiso, Chile",
            latitude=-33.05,
            longitude=-72.55,
        )
        inland_event = self._event(
            event_id="inland",
            place="19 km NE of Kathmandu, Nepal",
            latitude=27.8,
            longitude=85.5,
        )

        offshore_spec = renderer._region_for_event(offshore_event)
        inland_spec = renderer._region_for_event(inland_event)

        self.assertEqual(renderer._location_indicator(offshore_event, offshore_spec), "OFFSHORE")
        self.assertIsNone(renderer._location_indicator(inland_event, inland_spec))

    def _event(
        self,
        *,
        event_id: str,
        place: str,
        latitude: float,
        longitude: float,
    ) -> EarthquakeEvent:
        return EarthquakeEvent(
            event_id=event_id,
            updated_ms=1,
            magnitude=5.1,
            place=place,
            event_time=datetime(2026, 3, 30, 1, 12, tzinfo=timezone.utc),
            detail_url="https://example.com/detail",
            event_url="https://example.com/event",
            latitude=latitude,
            longitude=longitude,
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


if __name__ == "__main__":
    unittest.main()
