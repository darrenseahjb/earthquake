from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from earthquake_bot.map_shapes import REGION_POLYGONS
from earthquake_bot.models import EarthquakeEvent


@dataclass(frozen=True)
class MapLabel:
    text: str
    lon: float
    lat: float
    color: tuple[int, int, int] | None = None
    priority: int = 0
    padding: int = 4


@dataclass(frozen=True)
class RegionSpec:
    name: str
    lon_min: float
    lon_max: float
    lat_min: float
    lat_max: float
    polygons: tuple[tuple[tuple[float, float], ...], ...]
    labels: tuple[MapLabel, ...]
    water_labels: tuple[MapLabel, ...]


JAPAN_REGION = RegionSpec(
    name="Japan",
    lon_min=126.0,
    lon_max=149.0,
    lat_min=29.0,
    lat_max=47.0,
    polygons=(
        (
            (126.8, 34.3),
            (127.5, 35.0),
            (128.2, 35.8),
            (129.0, 36.7),
            (129.2, 37.8),
            (128.8, 38.8),
            (128.2, 39.7),
            (127.4, 40.6),
            (126.9, 40.5),
            (126.6, 39.4),
            (126.4, 38.3),
            (126.4, 37.0),
            (126.5, 35.7),
            (126.8, 34.3),
        ),
        (
            (129.2, 31.0),
            (129.8, 31.4),
            (130.5, 31.9),
            (131.2, 32.4),
            (131.4, 33.0),
            (131.0, 33.5),
            (130.2, 33.6),
            (129.5, 33.2),
            (129.0, 32.5),
            (128.9, 31.7),
            (129.2, 31.0),
        ),
        (
            (132.0, 33.2),
            (132.8, 33.3),
            (133.7, 33.6),
            (134.3, 33.9),
            (134.4, 34.2),
            (133.7, 34.3),
            (132.8, 34.1),
            (132.1, 33.8),
            (132.0, 33.2),
        ),
        (
            (130.9, 34.1),
            (131.8, 34.4),
            (132.8, 34.5),
            (133.8, 34.5),
            (134.7, 34.7),
            (135.5, 34.7),
            (136.3, 34.8),
            (137.0, 35.0),
            (137.8, 35.4),
            (138.6, 35.8),
            (139.4, 36.3),
            (140.2, 37.0),
            (140.9, 38.0),
            (141.4, 39.1),
            (141.6, 40.0),
            (141.3, 40.7),
            (140.5, 40.9),
            (139.6, 40.6),
            (138.8, 39.9),
            (138.0, 39.2),
            (137.2, 38.3),
            (136.3, 37.4),
            (135.4, 36.8),
            (134.6, 35.9),
            (133.8, 35.1),
            (133.0, 34.8),
            (132.2, 34.6),
            (131.5, 34.4),
            (130.9, 34.1),
        ),
        (
            (139.9, 41.4),
            (140.8, 41.7),
            (141.7, 42.0),
            (142.8, 42.5),
            (143.8, 43.0),
            (144.8, 43.6),
            (145.0, 44.2),
            (144.3, 44.6),
            (143.3, 44.9),
            (142.3, 44.5),
            (141.6, 44.0),
            (141.0, 43.3),
            (140.5, 42.6),
            (140.0, 41.9),
            (139.9, 41.4),
        ),
        (
            (141.8, 45.3),
            (142.3, 45.8),
            (142.9, 46.3),
            (143.6, 46.5),
            (143.9, 46.2),
            (143.6, 45.6),
            (143.0, 45.0),
            (142.4, 44.8),
            (141.9, 45.0),
            (141.8, 45.3),
        ),
        (
            (130.0, 33.0),
            (130.5, 33.3),
            (130.9, 33.6),
            (131.1, 34.0),
            (130.8, 34.2),
            (130.3, 34.1),
            (129.9, 33.7),
            (129.8, 33.3),
            (130.0, 33.0),
        ),
        (
            (130.2, 27.7),
            (130.8, 28.1),
            (131.2, 28.5),
            (131.2, 29.0),
            (130.8, 29.2),
            (130.3, 28.9),
            (130.1, 28.4),
            (130.2, 27.7),
        ),
        (
            (121.0, 22.0),
            (121.4, 22.4),
            (121.6, 23.1),
            (121.6, 24.0),
            (121.2, 24.9),
            (120.9, 25.3),
            (120.5, 24.8),
            (120.4, 24.0),
            (120.5, 23.1),
            (120.7, 22.5),
            (121.0, 22.0),
        ),
    ),
    labels=(
        MapLabel("HOKKAIDO", 143.2, 42.9, priority=6, padding=6),
        MapLabel("HONSHU", 137.1, 36.6, priority=5, padding=6),
        MapLabel("JAPAN", 139.0, 36.8, priority=5, padding=6),
        MapLabel("SHIKOKU", 133.5, 33.5, priority=5, padding=6),
        MapLabel("KYUSHU", 130.6, 32.6, priority=5, padding=6),
        MapLabel("KOREA", 127.7, 36.2, priority=4, padding=6),
        MapLabel("Tokyo", 139.7, 35.7, (224, 233, 244), priority=4),
        MapLabel("Sendai", 140.9, 38.3, (224, 233, 244), priority=4),
        MapLabel("Sapporo", 141.4, 42.9, (224, 233, 244), priority=4),
        MapLabel("Osaka", 135.5, 34.6, (224, 233, 244), priority=3),
        MapLabel("Nagoya", 136.9, 35.0, (224, 233, 244), priority=3),
        MapLabel("Fukuoka", 130.4, 33.6, (224, 233, 244), priority=2),
    ),
    water_labels=(
        MapLabel("Sea of Japan", 130.8, 39.2, priority=2, padding=6),
        MapLabel("Pacific Ocean", 145.5, 33.1, priority=1, padding=6),
        MapLabel("Japan Trench", 143.9, 38.6, priority=1, padding=6),
    ),
)


SE_ASIA_REGION = RegionSpec(
    name="Southeast Asia",
    lon_min=94.0,
    lon_max=138.0,
    lat_min=-13.0,
    lat_max=25.0,
    polygons=(
        (
            (99.0, 1.0),
            (100.5, 2.0),
            (101.8, 3.6),
            (102.6, 5.4),
            (103.4, 6.8),
            (103.5, 8.4),
            (102.9, 9.8),
            (101.8, 11.0),
            (100.9, 12.0),
            (100.0, 11.3),
            (99.5, 9.6),
            (99.2, 8.0),
            (99.0, 6.0),
            (98.7, 4.1),
            (98.7, 2.0),
            (99.0, 1.0),
        ),
        (
            (105.0, -6.2),
            (107.0, -6.4),
            (109.0, -6.8),
            (111.0, -7.3),
            (113.2, -7.7),
            (114.4, -8.0),
            (114.9, -8.2),
            (113.5, -8.5),
            (110.5, -8.4),
            (107.8, -8.2),
            (105.5, -7.6),
            (104.9, -6.8),
            (105.0, -6.2),
        ),
        (
            (95.0, 5.8),
            (96.8, 5.5),
            (98.3, 4.8),
            (99.8, 3.0),
            (100.9, 1.3),
            (101.4, -0.2),
            (101.8, -1.8),
            (102.2, -3.5),
            (103.0, -5.3),
            (104.0, -5.8),
            (104.6, -4.8),
            (104.6, -3.0),
            (104.0, -1.0),
            (103.1, 1.0),
            (102.2, 2.5),
            (100.9, 3.9),
            (99.0, 5.0),
            (97.0, 5.8),
            (95.0, 5.8),
        ),
        (
            (109.0, -4.0),
            (111.3, -2.3),
            (113.6, -0.8),
            (115.7, 0.7),
            (117.6, 2.3),
            (118.8, 4.0),
            (118.0, 5.9),
            (116.1, 6.6),
            (113.8, 6.6),
            (111.8, 5.6),
            (110.2, 3.8),
            (109.2, 1.6),
            (108.9, -0.5),
            (109.0, -4.0),
        ),
        (
            (119.5, -5.4),
            (120.7, -4.1),
            (121.8, -2.5),
            (122.2, -0.7),
            (123.0, 0.9),
            (124.2, 1.6),
            (124.2, 0.2),
            (123.4, -1.3),
            (122.8, -2.3),
            (123.8, -3.3),
            (124.7, -4.2),
            (124.0, -5.2),
            (122.5, -5.4),
            (121.1, -5.5),
            (119.5, -5.4),
        ),
        (
            (120.0, 5.5),
            (121.2, 6.4),
            (122.0, 7.9),
            (122.1, 9.8),
            (121.9, 11.7),
            (122.1, 13.6),
            (122.5, 15.2),
            (121.8, 16.7),
            (120.9, 17.8),
            (120.4, 18.9),
            (120.2, 17.0),
            (120.1, 15.2),
            (120.0, 13.4),
            (120.0, 11.5),
            (120.0, 9.6),
            (120.0, 7.6),
            (120.0, 5.5),
        ),
        (
            (123.0, 8.0),
            (124.4, 8.9),
            (125.8, 9.9),
            (126.0, 11.0),
            (125.0, 11.4),
            (123.7, 10.6),
            (123.0, 9.2),
            (123.0, 8.0),
        ),
        (
            (124.0, 5.0),
            (125.2, 6.0),
            (126.0, 7.4),
            (126.5, 8.6),
            (126.2, 9.5),
            (125.1, 9.7),
            (124.1, 9.0),
            (123.8, 7.5),
            (123.8, 6.0),
            (124.0, 5.0),
        ),
        (
            (119.7, 21.8),
            (120.5, 22.3),
            (121.1, 23.0),
            (121.4, 24.1),
            (121.3, 25.0),
            (120.9, 25.3),
            (120.5, 24.5),
            (120.1, 23.4),
            (119.8, 22.5),
            (119.7, 21.8),
        ),
        (
            (126.0, 0.3),
            (127.2, 0.8),
            (128.1, 1.5),
            (128.0, 2.4),
            (127.0, 2.4),
            (126.2, 1.6),
            (126.0, 0.3),
        ),
        (
            (130.0, -2.8),
            (132.0, -2.6),
            (134.0, -2.4),
            (136.2, -2.5),
            (137.6, -3.2),
            (137.4, -4.7),
            (135.4, -5.4),
            (132.6, -5.7),
            (130.3, -5.4),
            (129.8, -4.0),
            (130.0, -2.8),
        ),
    ),
    labels=(
        MapLabel("LUZON", 121.4, 15.4, priority=6, padding=6),
        MapLabel("VISAYAS", 123.8, 11.0, priority=5, padding=6),
        MapLabel("MINDANAO", 124.6, 8.0, priority=5, padding=6),
        MapLabel("TAIWAN", 121.1, 23.7, priority=5, padding=6),
        MapLabel("BORNEO", 114.4, 1.5, priority=5, padding=6),
        MapLabel("SULAWESI", 122.3, -2.1, priority=5, padding=6),
        MapLabel("JAVA", 110.4, -7.4, priority=5, padding=6),
        MapLabel("SUMATRA", 99.4, 0.4, priority=5, padding=6),
        MapLabel("PAPUA", 133.9, -3.5, priority=5, padding=6),
        MapLabel("Manila", 121.0, 14.6, (224, 233, 244), priority=4),
        MapLabel("Cebu", 123.9, 10.3, (224, 233, 244), priority=3),
        MapLabel("Davao", 125.6, 7.1, (224, 233, 244), priority=3),
        MapLabel("Jakarta", 106.8, -6.2, (224, 233, 244), priority=4),
        MapLabel("Surabaya", 112.7, -7.3, (224, 233, 244), priority=3),
        MapLabel("Kuala Lumpur", 101.7, 3.1, (224, 233, 244), priority=3),
        MapLabel("Makassar", 119.4, -5.1, (224, 233, 244), priority=3),
        MapLabel("Taipei", 121.5, 25.0, (224, 233, 244), priority=4),
    ),
    water_labels=(
        MapLabel("Philippine Sea", 132.0, 12.0, priority=2, padding=6),
        MapLabel("South China Sea", 112.0, 15.0, priority=2, padding=6),
        MapLabel("Java Sea", 112.0, -5.0, priority=1, padding=6),
        MapLabel("Celebes Sea", 121.7, 5.3, priority=1, padding=6),
        MapLabel("Banda Sea", 129.0, -5.7, priority=1, padding=6),
    ),
)


HIMALAYA_REGION = RegionSpec(
    name="Himalaya",
    lon_min=76.0,
    lon_max=97.0,
    lat_min=24.0,
    lat_max=36.0,
    polygons=(
        (
            (77.0, 26.0),
            (79.0, 26.5),
            (81.2, 27.0),
            (83.4, 27.6),
            (85.6, 28.1),
            (87.6, 28.6),
            (89.4, 29.1),
            (91.0, 29.6),
            (93.0, 30.0),
            (94.0, 30.8),
            (93.2, 31.8),
            (91.0, 32.2),
            (88.5, 31.8),
            (86.0, 31.2),
            (83.2, 30.4),
            (80.6, 29.5),
            (78.5, 28.2),
            (77.0, 26.8),
            (77.0, 26.0),
        ),
    ),
    labels=(
        MapLabel("NEPAL", 84.2, 28.2, priority=6, padding=6),
        MapLabel("HIMALAYA", 86.8, 30.9, priority=5, padding=6),
        MapLabel("Kathmandu", 85.3, 27.7, (224, 233, 244), priority=4),
        MapLabel("Pokhara", 84.0, 28.2, (224, 233, 244), priority=2),
        MapLabel("India", 80.5, 26.5, (224, 233, 244), priority=2),
        MapLabel("Tibet", 89.4, 30.8, (224, 233, 244), priority=2),
    ),
    water_labels=(
        MapLabel("Gangetic Plain", 82.8, 25.5, priority=1, padding=6),
    ),
)


ICELAND_REGION = RegionSpec(
    name="Iceland",
    lon_min=-29.0,
    lon_max=-11.0,
    lat_min=62.0,
    lat_max=68.5,
    polygons=(
        (
            (-24.5, 63.7),
            (-23.0, 63.2),
            (-20.0, 63.4),
            (-17.4, 64.0),
            (-15.2, 64.8),
            (-14.0, 65.8),
            (-14.5, 66.6),
            (-16.6, 67.1),
            (-19.5, 67.3),
            (-22.2, 66.8),
            (-24.0, 65.8),
            (-24.8, 64.6),
            (-24.5, 63.7),
        ),
    ),
    labels=(
        MapLabel("ICELAND", -19.0, 64.8, priority=6, padding=6),
        MapLabel("Reykjavik", -21.9, 64.1, (224, 233, 244), priority=4),
        MapLabel("Akureyri", -18.1, 65.7, (224, 233, 244), priority=3),
    ),
    water_labels=(
        MapLabel("North Atlantic", -20.5, 63.0, priority=2, padding=6),
        MapLabel("Greenland Sea", -16.7, 67.3, priority=1, padding=6),
    ),
)


ALASKA_REGION = RegionSpec(
    name="Alaska",
    lon_min=-178.0,
    lon_max=-130.0,
    lat_min=50.0,
    lat_max=67.0,
    polygons=(
        (
            (-170.0, 54.7),
            (-166.0, 56.0),
            (-162.0, 58.0),
            (-157.0, 59.3),
            (-152.0, 61.3),
            (-148.0, 63.0),
            (-143.0, 63.6),
            (-138.0, 60.8),
            (-140.0, 58.2),
            (-146.0, 56.0),
            (-153.0, 54.8),
            (-161.0, 54.2),
            (-167.0, 54.1),
            (-170.0, 54.7),
        ),
        (
            (-177.0, 51.8),
            (-174.0, 52.2),
            (-171.0, 52.6),
            (-168.0, 53.0),
            (-165.0, 53.4),
            (-162.0, 53.2),
            (-164.0, 52.6),
            (-168.0, 52.2),
            (-172.0, 51.9),
            (-175.0, 51.6),
            (-177.0, 51.8),
        ),
        (
            (-141.0, 55.0),
            (-137.5, 56.2),
            (-135.5, 58.0),
            (-135.0, 59.2),
            (-136.5, 59.4),
            (-138.5, 58.5),
            (-140.5, 56.8),
            (-141.0, 55.0),
        ),
    ),
    labels=(
        MapLabel("ALASKA", -151.5, 60.2, priority=6, padding=6),
        MapLabel("ALEUTIANS", -169.5, 52.7, priority=5, padding=6),
        MapLabel("Anchorage", -149.9, 61.2, (224, 233, 244), priority=4),
        MapLabel("Fairbanks", -147.7, 64.8, (224, 233, 244), priority=3),
        MapLabel("Juneau", -134.4, 58.3, (224, 233, 244), priority=2),
    ),
    water_labels=(
        MapLabel("Gulf of Alaska", -145.0, 55.5, priority=2, padding=6),
        MapLabel("Bering Sea", -167.0, 58.4, priority=2, padding=6),
        MapLabel("North Pacific", -159.0, 52.3, priority=1, padding=6),
    ),
)


CALIFORNIA_REGION = RegionSpec(
    name="California",
    lon_min=-126.0,
    lon_max=-112.0,
    lat_min=31.0,
    lat_max=42.5,
    polygons=(
        (
            (-124.4, 32.5),
            (-124.3, 34.5),
            (-124.1, 37.0),
            (-123.7, 39.5),
            (-123.2, 41.3),
            (-122.3, 41.9),
            (-120.6, 41.8),
            (-119.3, 39.8),
            (-118.4, 37.5),
            (-117.6, 35.5),
            (-116.5, 34.2),
            (-115.0, 32.7),
            (-114.5, 32.2),
            (-117.0, 32.4),
            (-119.0, 33.7),
            (-120.5, 35.0),
            (-121.7, 36.5),
            (-122.7, 38.5),
            (-123.6, 40.2),
            (-124.4, 32.5),
        ),
        (
            (-115.5, 28.3),
            (-114.6, 29.5),
            (-113.8, 30.9),
            (-113.2, 32.0),
            (-112.7, 30.8),
            (-112.8, 29.0),
            (-113.5, 27.5),
            (-114.8, 27.0),
            (-115.5, 28.3),
        ),
    ),
    labels=(
        MapLabel("CALIFORNIA", -120.0, 37.2, priority=6, padding=6),
        MapLabel("BAJA", -114.1, 29.8, priority=5, padding=6),
        MapLabel("San Francisco", -122.4, 37.8, (224, 233, 244), priority=4),
        MapLabel("Sacramento", -121.5, 38.6, (224, 233, 244), priority=3),
        MapLabel("Los Angeles", -118.2, 34.1, (224, 233, 244), priority=4),
        MapLabel("San Diego", -117.2, 32.7, (224, 233, 244), priority=3),
    ),
    water_labels=(
        MapLabel("Pacific Ocean", -121.2, 33.0, priority=2, padding=6),
        MapLabel("San Andreas", -119.1, 36.1, priority=1, padding=6),
    ),
)


MEXICO_CENTRAL_AMERICA_REGION = RegionSpec(
    name="Mexico and Central America",
    lon_min=-111.0,
    lon_max=-77.0,
    lat_min=6.0,
    lat_max=24.0,
    polygons=(
        (
            (-108.0, 22.8),
            (-105.0, 23.5),
            (-102.0, 23.0),
            (-99.0, 22.2),
            (-96.0, 20.5),
            (-94.0, 18.7),
            (-92.0, 17.2),
            (-91.0, 16.0),
            (-92.5, 15.2),
            (-95.0, 15.6),
            (-98.0, 17.0),
            (-101.0, 18.6),
            (-104.0, 20.1),
            (-107.0, 21.5),
            (-108.0, 22.8),
        ),
        (
            (-92.5, 15.2),
            (-90.5, 15.0),
            (-88.8, 14.8),
            (-87.2, 14.2),
            (-85.8, 13.0),
            (-84.6, 11.5),
            (-83.9, 10.0),
            (-83.3, 8.8),
            (-82.7, 8.0),
            (-81.7, 8.4),
            (-82.1, 9.5),
            (-83.2, 10.8),
            (-84.2, 12.0),
            (-85.6, 13.3),
            (-87.3, 14.3),
            (-89.0, 14.9),
            (-90.9, 15.1),
            (-92.5, 15.2),
        ),
    ),
    labels=(
        MapLabel("MEXICO", -101.0, 19.8, priority=6, padding=6),
        MapLabel("GUATEMALA", -90.6, 15.3, priority=5, padding=6),
        MapLabel("COSTA RICA", -84.1, 9.9, priority=5, padding=6),
        MapLabel("Mexico City", -99.1, 19.4, (224, 233, 244), priority=4),
        MapLabel("Oaxaca", -96.7, 17.1, (224, 233, 244), priority=3),
        MapLabel("Guatemala City", -90.5, 14.6, (224, 233, 244), priority=3),
        MapLabel("San Jose", -84.1, 9.9, (224, 233, 244), priority=3),
    ),
    water_labels=(
        MapLabel("Pacific Ocean", -96.0, 10.2, priority=2, padding=6),
        MapLabel("Caribbean Sea", -84.0, 16.8, priority=2, padding=6),
        MapLabel("Cocos Plate", -90.2, 8.0, priority=1, padding=6),
    ),
)


CARIBBEAN_REGION = RegionSpec(
    name="Caribbean",
    lon_min=-71.0,
    lon_max=-60.0,
    lat_min=16.0,
    lat_max=22.5,
    polygons=(
        (
            (-70.8, 18.1),
            (-69.5, 18.5),
            (-68.0, 19.0),
            (-69.0, 20.0),
            (-70.5, 20.1),
            (-71.0, 19.2),
            (-70.8, 18.1),
        ),
        (
            (-67.4, 17.8),
            (-65.1, 18.0),
            (-64.4, 18.4),
            (-65.0, 18.7),
            (-66.5, 18.6),
            (-67.4, 17.8),
        ),
    ),
    labels=(
        MapLabel("PUERTO RICO", -66.3, 18.3, priority=6, padding=6),
        MapLabel("HISPANIOLA", -69.2, 19.2, priority=4, padding=6),
        MapLabel("San Juan", -66.1, 18.4, (224, 233, 244), priority=4),
    ),
    water_labels=(
        MapLabel("Caribbean Sea", -66.2, 17.0, priority=2, padding=6),
        MapLabel("Atlantic Ocean", -65.3, 21.1, priority=1, padding=6),
    ),
)


ANDES_REGION = RegionSpec(
    name="Andes",
    lon_min=-82.0,
    lon_max=-58.0,
    lat_min=-42.0,
    lat_max=14.0,
    polygons=(
        (
            (-79.0, 9.0),
            (-78.0, 6.0),
            (-77.0, 2.0),
            (-78.0, -3.0),
            (-79.0, -9.0),
            (-78.0, -15.0),
            (-76.0, -22.0),
            (-74.0, -30.0),
            (-72.0, -36.0),
            (-70.0, -40.0),
            (-66.0, -39.0),
            (-64.0, -32.0),
            (-64.0, -24.0),
            (-65.0, -16.0),
            (-67.0, -8.0),
            (-69.0, -2.0),
            (-72.0, 4.0),
            (-75.0, 8.0),
            (-79.0, 9.0),
        ),
    ),
    labels=(
        MapLabel("COLOMBIA", -74.5, 5.5, priority=6, padding=6),
        MapLabel("ECUADOR", -78.3, -1.2, priority=5, padding=6),
        MapLabel("PERU", -75.5, -10.0, priority=5, padding=6),
        MapLabel("CHILE", -71.0, -26.0, priority=5, padding=6),
        MapLabel("BOLIVIA", -64.9, -17.0, priority=5, padding=6),
        MapLabel("ARGENTINA", -66.2, -31.0, priority=4, padding=6),
        MapLabel("Bogota", -74.1, 4.7, (224, 233, 244), priority=4),
        MapLabel("Quito", -78.5, -0.2, (224, 233, 244), priority=3),
        MapLabel("Lima", -77.0, -12.0, (224, 233, 244), priority=3),
        MapLabel("Santiago", -70.7, -33.5, (224, 233, 244), priority=4),
        MapLabel("La Paz", -68.1, -16.5, (224, 233, 244), priority=3),
    ),
    water_labels=(
        MapLabel("Pacific Ocean", -79.0, -12.0, priority=2, padding=6),
        MapLabel("Andes", -70.5, -11.0, priority=2, padding=6),
    ),
)


MEDITERRANEAN_REGION = RegionSpec(
    name="Mediterranean",
    lon_min=-12.0,
    lon_max=42.0,
    lat_min=27.0,
    lat_max=48.0,
    polygons=(
        (
            (-10.5, 36.0),
            (-10.0, 38.5),
            (-9.5, 41.5),
            (-8.7, 43.2),
            (-5.5, 43.6),
            (-1.5, 43.4),
            (2.5, 42.6),
            (4.0, 41.0),
            (2.0, 39.8),
            (-0.5, 38.7),
            (-3.0, 37.0),
            (-6.5, 36.0),
            (-10.5, 36.0),
        ),
        (
            (7.2, 44.8),
            (9.5, 45.2),
            (12.5, 44.8),
            (14.8, 43.5),
            (16.2, 41.5),
            (16.6, 39.0),
            (15.8, 37.0),
            (14.5, 37.5),
            (13.6, 39.5),
            (12.5, 41.3),
            (11.2, 42.7),
            (9.5, 44.0),
            (7.2, 44.8),
        ),
        (
            (13.0, 45.0),
            (17.5, 46.0),
            (22.5, 45.7),
            (27.0, 45.0),
            (32.0, 43.8),
            (37.5, 41.8),
            (40.5, 39.8),
            (39.2, 37.2),
            (34.2, 36.1),
            (29.0, 36.4),
            (24.0, 37.2),
            (20.0, 38.8),
            (17.0, 40.5),
            (14.5, 42.8),
            (13.0, 45.0),
        ),
        (
            (-10.5, 30.2),
            (-4.0, 31.2),
            (3.5, 32.0),
            (11.5, 33.1),
            (20.0, 33.7),
            (28.0, 33.4),
            (34.0, 32.0),
            (35.5, 30.2),
            (28.0, 29.0),
            (17.0, 29.2),
            (6.0, 29.6),
            (-4.0, 29.9),
            (-10.5, 30.2),
        ),
    ),
    labels=(
        MapLabel("PORTUGAL", -8.2, 39.5, priority=6, padding=6),
        MapLabel("ITALY", 12.5, 42.0, priority=6, padding=6),
        MapLabel("GREECE", 22.5, 39.0, priority=5, padding=6),
        MapLabel("TURKEY", 32.2, 39.3, priority=6, padding=6),
        MapLabel("ROMANIA", 26.0, 45.3, priority=5, padding=6),
        MapLabel("MOROCCO", -6.0, 32.7, priority=5, padding=6),
        MapLabel("ALGERIA", 3.0, 34.0, priority=5, padding=6),
        MapLabel("Lisbon", -9.1, 38.7, (224, 233, 244), priority=4),
        MapLabel("Rome", 12.5, 41.9, (224, 233, 244), priority=4),
        MapLabel("Athens", 23.7, 37.9, (224, 233, 244), priority=3),
        MapLabel("Istanbul", 29.0, 41.0, (224, 233, 244), priority=4),
        MapLabel("Bucharest", 26.1, 44.4, (224, 233, 244), priority=3),
        MapLabel("Algiers", 3.1, 36.7, (224, 233, 244), priority=3),
    ),
    water_labels=(
        MapLabel("Mediterranean Sea", 15.0, 37.5, priority=2, padding=6),
        MapLabel("Aegean Sea", 24.0, 38.5, priority=1, padding=6),
        MapLabel("Black Sea", 31.0, 44.5, priority=1, padding=6),
    ),
)


EAST_AFRICA_REGION = RegionSpec(
    name="East Africa",
    lon_min=28.0,
    lon_max=50.0,
    lat_min=-13.0,
    lat_max=18.0,
    polygons=(
        (
            (29.0, -11.5),
            (31.5, -10.0),
            (34.0, -8.0),
            (36.5, -6.0),
            (39.0, -2.0),
            (41.0, 1.5),
            (43.0, 4.5),
            (45.5, 8.0),
            (47.5, 11.5),
            (47.0, 15.0),
            (43.5, 15.8),
            (40.0, 13.0),
            (37.5, 9.0),
            (35.5, 5.0),
            (34.0, 1.0),
            (33.0, -3.0),
            (32.0, -7.0),
            (30.0, -10.0),
            (29.0, -11.5),
        ),
    ),
    labels=(
        MapLabel("ETHIOPIA", 39.0, 9.0, priority=6, padding=6),
        MapLabel("KENYA", 37.0, 0.5, priority=5, padding=6),
        MapLabel("UGANDA", 32.5, 1.5, priority=5, padding=6),
        MapLabel("TANZANIA", 35.0, -6.0, priority=5, padding=6),
        MapLabel("Addis Ababa", 38.8, 9.0, (224, 233, 244), priority=4),
        MapLabel("Nairobi", 36.8, -1.3, (224, 233, 244), priority=4),
        MapLabel("Kampala", 32.6, 0.3, (224, 233, 244), priority=3),
        MapLabel("Dar es Salaam", 39.3, -6.8, (224, 233, 244), priority=3),
    ),
    water_labels=(
        MapLabel("Indian Ocean", 44.4, -4.0, priority=2, padding=6),
        MapLabel("Lake Victoria", 33.2, -0.8, priority=1, padding=6),
        MapLabel("East African Rift", 36.0, 5.0, priority=1, padding=6),
    ),
)


SOUTHWEST_PACIFIC_REGION = RegionSpec(
    name="Southwest Pacific",
    lon_min=140.0,
    lon_max=180.0,
    lat_min=-25.0,
    lat_max=5.0,
    polygons=(
        (
            (141.0, -8.5),
            (144.5, -8.0),
            (148.5, -6.8),
            (152.0, -5.8),
            (155.0, -5.5),
            (155.5, -7.5),
            (152.0, -9.0),
            (148.0, -9.5),
            (144.0, -9.2),
            (141.0, -8.5),
        ),
        (
            (155.5, -5.8),
            (158.0, -6.2),
            (160.8, -7.0),
            (162.8, -8.5),
            (161.5, -9.6),
            (158.5, -9.1),
            (156.0, -8.2),
            (155.5, -5.8),
        ),
        (
            (166.0, -13.0),
            (167.5, -13.5),
            (168.5, -15.0),
            (169.0, -17.0),
            (168.3, -19.0),
            (167.0, -18.5),
            (166.2, -16.5),
            (166.0, -13.0),
        ),
        (
            (176.4, -16.0),
            (177.5, -16.4),
            (178.6, -17.3),
            (178.2, -18.6),
            (177.0, -18.8),
            (176.0, -17.8),
            (176.4, -16.0),
        ),
    ),
    labels=(
        MapLabel("PAPUA NEW GUINEA", 147.8, -6.3, priority=6, padding=6),
        MapLabel("SOLOMONS", 159.3, -8.2, priority=5, padding=6),
        MapLabel("VANUATU", 167.8, -16.5, priority=5, padding=6),
        MapLabel("FIJI", 177.2, -17.7, priority=5, padding=6),
        MapLabel("Port Moresby", 147.2, -9.4, (224, 233, 244), priority=4),
        MapLabel("Honiara", 160.0, -9.4, (224, 233, 244), priority=3),
        MapLabel("Port Vila", 168.3, -17.7, (224, 233, 244), priority=3),
        MapLabel("Suva", 178.4, -18.1, (224, 233, 244), priority=3),
    ),
    water_labels=(
        MapLabel("Coral Sea", 153.0, -15.0, priority=2, padding=6),
        MapLabel("South Pacific", 171.0, -12.0, priority=2, padding=6),
        MapLabel("Bismarck Sea", 148.0, -3.0, priority=1, padding=6),
    ),
)


TONGA_REGION = RegionSpec(
    name="Tonga",
    lon_min=-179.0,
    lon_max=-170.0,
    lat_min=-25.0,
    lat_max=-12.0,
    polygons=(
        (
            (-176.8, -15.0),
            (-176.0, -16.2),
            (-175.6, -17.8),
            (-175.3, -19.5),
            (-175.1, -21.2),
            (-174.6, -22.0),
            (-174.2, -20.2),
            (-174.3, -18.0),
            (-174.9, -16.0),
            (-175.6, -14.6),
            (-176.8, -15.0),
        ),
    ),
    labels=(
        MapLabel("TONGA", -175.3, -19.0, priority=6, padding=6),
        MapLabel("Nuku'alofa", -175.2, -21.1, (224, 233, 244), priority=4),
    ),
    water_labels=(
        MapLabel("South Pacific", -174.0, -13.8, priority=2, padding=6),
    ),
)


NEW_ZEALAND_REGION = RegionSpec(
    name="New Zealand",
    lon_min=164.0,
    lon_max=180.0,
    lat_min=-49.0,
    lat_max=-33.0,
    polygons=(
        (
            (166.0, -46.8),
            (167.8, -46.0),
            (169.8, -45.0),
            (171.8, -44.0),
            (173.0, -42.8),
            (173.6, -41.5),
            (172.8, -40.8),
            (171.0, -41.2),
            (169.5, -42.2),
            (168.2, -43.6),
            (166.8, -45.0),
            (166.0, -46.8),
        ),
        (
            (173.2, -41.4),
            (174.4, -40.8),
            (175.6, -39.8),
            (176.7, -38.5),
            (176.8, -37.2),
            (175.9, -36.2),
            (174.6, -36.0),
            (173.4, -36.8),
            (172.8, -38.0),
            (172.6, -39.5),
            (173.2, -41.4),
        ),
    ),
    labels=(
        MapLabel("SOUTH ISLAND", 170.0, -43.2, priority=6, padding=6),
        MapLabel("NORTH ISLAND", 175.0, -38.3, priority=6, padding=6),
        MapLabel("Auckland", 174.8, -36.9, (224, 233, 244), priority=4),
        MapLabel("Wellington", 174.8, -41.3, (224, 233, 244), priority=4),
        MapLabel("Christchurch", 172.6, -43.5, (224, 233, 244), priority=3),
    ),
    water_labels=(
        MapLabel("Tasman Sea", 167.0, -40.5, priority=2, padding=6),
        MapLabel("Pacific Ocean", 177.0, -42.0, priority=2, padding=6),
    ),
)


def _with_loaded_polygons(spec: RegionSpec, shape_key: str) -> RegionSpec:
    return RegionSpec(
        name=spec.name,
        lon_min=spec.lon_min,
        lon_max=spec.lon_max,
        lat_min=spec.lat_min,
        lat_max=spec.lat_max,
        polygons=tuple(REGION_POLYGONS[shape_key]),
        labels=spec.labels,
        water_labels=spec.water_labels,
    )


JAPAN_REGION = _with_loaded_polygons(JAPAN_REGION, "JAPAN")
SE_ASIA_REGION = _with_loaded_polygons(SE_ASIA_REGION, "SE_ASIA")
HIMALAYA_REGION = _with_loaded_polygons(HIMALAYA_REGION, "HIMALAYA")
ICELAND_REGION = _with_loaded_polygons(ICELAND_REGION, "ICELAND")
ALASKA_REGION = _with_loaded_polygons(ALASKA_REGION, "ALASKA")
MEXICO_CENTRAL_AMERICA_REGION = _with_loaded_polygons(MEXICO_CENTRAL_AMERICA_REGION, "MEXICO_CA")
CARIBBEAN_REGION = _with_loaded_polygons(CARIBBEAN_REGION, "CARIBBEAN")
ANDES_REGION = _with_loaded_polygons(ANDES_REGION, "ANDES")
MEDITERRANEAN_REGION = _with_loaded_polygons(MEDITERRANEAN_REGION, "MEDITERRANEAN")
EAST_AFRICA_REGION = _with_loaded_polygons(EAST_AFRICA_REGION, "EAST_AFRICA")
SOUTHWEST_PACIFIC_REGION = _with_loaded_polygons(SOUTHWEST_PACIFIC_REGION, "SOUTHWEST_PACIFIC")
NEW_ZEALAND_REGION = _with_loaded_polygons(NEW_ZEALAND_REGION, "NEW_ZEALAND")


DETAILED_REGION_SPECS = (
    JAPAN_REGION,
    SE_ASIA_REGION,
    HIMALAYA_REGION,
    ICELAND_REGION,
    ALASKA_REGION,
    CALIFORNIA_REGION,
    MEXICO_CENTRAL_AMERICA_REGION,
    CARIBBEAN_REGION,
    ANDES_REGION,
    MEDITERRANEAN_REGION,
    EAST_AFRICA_REGION,
    SOUTHWEST_PACIFIC_REGION,
    TONGA_REGION,
    NEW_ZEALAND_REGION,
)


GENERIC_LABEL_COLOR = (230, 238, 245)


class AlertCardRenderer:
    def __init__(self) -> None:
        self.bg = (7, 18, 32)
        self.panel = (12, 27, 48)
        self.map_bg = (9, 23, 41)
        self.grid = (42, 72, 104)
        self.border = (86, 118, 158)
        self.land = (85, 117, 101)
        self.land_edge = (222, 231, 236)
        self.water_label = (125, 149, 171)
        self.text_main = (245, 247, 250)
        self.text_sub = (172, 187, 204)
        self.text_soft = (135, 155, 176)

    def render_card(
        self,
        event: EarthquakeEvent,
        local_time: str,
        title: str,
        advisories: list[str],
    ) -> bytes:
        image = Image.new('RGB', (1400, 900), self.bg)
        draw = ImageDraw.Draw(image)

        outer_box = (26, 26, 1374, 874)
        detail_box = (54, 54, 1348, 408)
        map_box = (54, 430, 1348, 844)

        self._rounded_panel(draw, outer_box, self.panel, radius=28, outline=self.border, width=2)
        self._rounded_panel(draw, detail_box, (15, 31, 54), radius=24, outline=self.border, width=2)
        self._rounded_panel(draw, map_box, self.map_bg, radius=24, outline=self.border, width=2)

        accent = self._accent_for_event(event)
        glow = self._accent_glow_for_event(event)
        spec = self._region_for_event(event)
        badge_font = self._font(24, bold=True)
        magnitude_font = self._mono_font(64)
        place_font = self._font(40, bold=True)
        advisory_font = self._font(22)
        meta_label_font = self._font(18, bold=True)
        meta_value_font = self._font(22)
        map_label_font = self._font(18, bold=True)
        city_label_font = self._font(16)
        source_label_font = self._font(15, bold=True)
        source_value_font = self._font(17)

        badge_text = title.upper().replace('QUAKE ', '')
        badge_box = (76, 72, 328, 124)
        self._rounded_panel(draw, badge_box, accent, radius=16)
        badge_width = draw.textlength(badge_text, font=badge_font)
        badge_x = badge_box[0] + (badge_box[2] - badge_box[0] - badge_width) / 2
        draw.text((badge_x, 84), badge_text, fill=self.bg, font=badge_font)

        draw.text((76, 156), f'M{self._format_magnitude(event.magnitude)}', fill=accent, font=magnitude_font)

        place_lines = self._wrap_text(event.place, place_font, 760, draw)[:2]
        self._draw_text_block(
            draw,
            place_lines,
            left=300,
            top=154,
            font=place_font,
            fill=self.text_main,
            line_gap=6,
        )

        advisory_text = ' '.join(item.strip() for item in advisories[:2] if item.strip())
        if advisory_text:
            advisory_lines = self._wrap_text(advisory_text, advisory_font, 900, draw)[:2]
            self._draw_text_block(
                draw,
                advisory_lines,
                left=76,
                top=250,
                font=advisory_font,
                fill=self.text_main,
                line_gap=4,
            )

        location_indicator = self._location_indicator(event, spec)
        if location_indicator:
            pill_box = (1038, 232, 1272, 278)
            self._rounded_panel(draw, pill_box, (19, 39, 66), radius=16, outline=accent, width=2)
            pill_font = self._font(18, bold=True)
            pill_width = draw.textlength(location_indicator, font=pill_font)
            pill_x = pill_box[0] + (pill_box[2] - pill_box[0] - pill_width) / 2
            draw.text((pill_x, pill_box[1] + 11), location_indicator, fill=accent, font=pill_font)

        chip_top = 308
        chip_width = 238
        chip_gap = 18
        chip_height = 74
        chip_specs = [
            ('LOCAL TIME', self._compact_local_time(local_time)),
            ('DEPTH', f'{event.depth_km:.1f} km' if event.depth_km is not None else 'Unavailable'),
            ('SIGNIFICANCE', str(event.significance) if event.significance is not None else 'N/A'),
        ]
        for index, (label, value) in enumerate(chip_specs):
            left = 76 + index * (chip_width + chip_gap)
            chip_box = (left, chip_top, left + chip_width, chip_top + chip_height)
            self._rounded_panel(draw, chip_box, (19, 39, 66), radius=18, outline=self.grid, width=1)
            draw.text((left + 16, chip_top + 12), label, fill=self.text_soft, font=meta_label_font)
            value_font = self._font(19) if label == 'LOCAL TIME' else meta_value_font
            value_lines = self._wrap_text(value, value_font, chip_width - 32, draw)[:1]
            self._draw_text_block(
                draw,
                value_lines,
                left=left + 16,
                top=chip_top + 34,
                font=value_font,
                fill=self.text_main,
                line_gap=2,
            )

        source_left = 1040
        source_box = (source_left - 18, chip_top, detail_box[2] - 26, chip_top + chip_height)
        self._rounded_panel(draw, source_box, (19, 39, 66), radius=18, outline=self.grid, width=1)
        source_top = chip_top + 12
        draw.text((source_left, source_top), 'OFFICIAL SOURCE', fill=self.text_soft, font=source_label_font)
        source_text = 'USGS realtime feed'
        if event.shakemap_url:
            source_text += ' | ShakeMap'
        source_lines = self._wrap_text(source_text, source_value_font, 250, draw)[:2]
        self._draw_text_block(
            draw,
            source_lines,
            left=source_left,
            top=source_top + 18,
            font=source_value_font,
            fill=self.text_main,
            line_gap=4,
        )

        self._draw_map(draw, event, spec, map_box, map_label_font, city_label_font, accent, glow)

        output = io.BytesIO()
        image.save(output, format='PNG', optimize=True)
        return output.getvalue()

    def _draw_map(
        self,
        draw: ImageDraw.ImageDraw,
        event: EarthquakeEvent,
        spec: RegionSpec,
        box: tuple[int, int, int, int],
        map_label_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        city_label_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        accent: tuple[int, int, int],
        glow: tuple[int, int, int],
    ) -> None:
        left, top, right, bottom = box
        plot_box = (left + 54, top + 14, right - 14, bottom - 96)
        plot_left, plot_top, plot_right, plot_bottom = plot_box
        self._draw_grid(draw, spec, plot_box)

        for polygon in spec.polygons:
            if not self._polygon_intersects_view(polygon, spec):
                continue
            self._draw_polygon(draw, polygon, spec, plot_box, self.land, self.land_edge)

        occupied_labels: list[tuple[int, int, int, int]] = []
        self._draw_map_labels(
            draw,
            spec.labels,
            spec,
            plot_box,
            default_font=map_label_font,
            city_font=city_label_font,
            occupied=occupied_labels,
        )
        self._draw_map_labels(
            draw,
            spec.water_labels,
            spec,
            plot_box,
            default_font=self._font(21, italic=True),
            city_font=self._font(21, italic=True),
            occupied=occupied_labels,
            default_fill=self.water_label,
            padding=6,
        )

        if event.latitude is None or event.longitude is None:
            return

        pin_x, pin_y = self._project(event.longitude, event.latitude, spec, plot_box)
        draw.line((pin_x, plot_top + 8, pin_x, plot_bottom - 8), fill=(*glow, 120), width=2)
        draw.line((plot_left + 8, pin_y, plot_right - 8, pin_y), fill=(*glow, 120), width=2)
        draw.ellipse((pin_x - 24, pin_y - 24, pin_x + 24, pin_y + 24), fill=(*glow, 96))
        draw.ellipse((pin_x - 12, pin_y - 12, pin_x + 12, pin_y + 12), fill=glow)
        draw.ellipse((pin_x - 7, pin_y - 7, pin_x + 7, pin_y + 7), fill=accent)

        footer_font = self._mono_font(18)
        coordinates = f'{self._format_coordinate(event.latitude, "N", "S")}, {self._format_coordinate(event.longitude, "E", "W")}'
        depth_text = f'{event.depth_km:.1f} km depth' if event.depth_km is not None else 'Depth unavailable'
        footer = f'M{self._format_magnitude(event.magnitude)} | {depth_text} | {self._short_place(event.place)}'
        footer_y = plot_bottom + 56
        draw.text((plot_left + 10, footer_y), coordinates, fill=self.text_main, font=footer_font)
        trimmed_footer = self._truncate_text(footer, footer_font, max_width=(plot_right - plot_left) - 215, draw=draw)
        draw.text((plot_left + 186, footer_y), trimmed_footer, fill=self.text_sub, font=footer_font)

    def _draw_grid(self, draw: ImageDraw.ImageDraw, spec: RegionSpec, box: tuple[int, int, int, int]) -> None:
        left, top, right, bottom = box
        lon_step = max(2, int(round((spec.lon_max - spec.lon_min) / 6)))
        lat_step = max(2, int(round((spec.lat_max - spec.lat_min) / 6)))
        for lon in range(int(spec.lon_min // lon_step * lon_step), int(spec.lon_max) + lon_step, lon_step):
            if lon <= spec.lon_min or lon >= spec.lon_max:
                continue
            x, _ = self._project(lon, spec.lat_min, spec, box)
            draw.line((x, top, x, bottom), fill=self.grid, width=1)
            draw.text((x, bottom + 10), self._format_axis_label(lon, 'E', 'W'), fill=self.text_soft, font=self._font(16), anchor='ma')
        for lat in range(int(spec.lat_min // lat_step * lat_step), int(spec.lat_max) + lat_step, lat_step):
            if lat <= spec.lat_min or lat >= spec.lat_max:
                continue
            _, y = self._project(spec.lon_min, lat, spec, box)
            draw.line((left, y, right, y), fill=self.grid, width=1)
            draw.text((left - 10, y), self._format_axis_label(lat, 'N', 'S'), fill=self.text_soft, font=self._font(16), anchor='rm')

    def _draw_polygon(
        self,
        draw: ImageDraw.ImageDraw,
        polygon: tuple[tuple[float, float], ...],
        spec: RegionSpec,
        box: tuple[int, int, int, int],
        fill: tuple[int, int, int],
        outline: tuple[int, int, int],
    ) -> None:
        points = [self._project(lon, lat, spec, box) for lon, lat in polygon]
        draw.polygon(points, fill=fill, outline=outline)

    def _draw_map_labels(
        self,
        draw: ImageDraw.ImageDraw,
        labels: tuple[MapLabel, ...],
        spec: RegionSpec,
        box: tuple[int, int, int, int],
        *,
        default_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        city_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        occupied: list[tuple[int, int, int, int]],
        default_fill: tuple[int, int, int] | None = None,
        padding: int = 4,
    ) -> None:
        ordered_labels = sorted(labels, key=lambda label: label.priority, reverse=True)
        for label in ordered_labels:
            if not self._point_in_view(label.lon, label.lat, spec):
                continue
            position = self._project(label.lon, label.lat, spec, box)
            font = city_font if label.color is not None else default_font
            fill = label.color or default_fill or self.text_main
            candidate = self._expand_box(
                draw.textbbox(position, label.text, font=font, anchor='mm'),
                label.padding or padding,
            )
            if any(self._boxes_intersect(candidate, existing) for existing in occupied):
                continue
            draw.text(position, label.text, fill=fill, font=font, anchor='mm')
            occupied.append(candidate)

    def _project(
        self,
        lon: float,
        lat: float,
        spec: RegionSpec,
        box: tuple[int, int, int, int],
    ) -> tuple[int, int]:
        left, top, right, bottom = box
        width = right - left
        height = bottom - top
        x = left + int(round((lon - spec.lon_min) / (spec.lon_max - spec.lon_min) * width))
        y = top + int(round((spec.lat_max - lat) / (spec.lat_max - spec.lat_min) * height))
        x = max(left, min(right, x))
        y = max(top, min(bottom, y))
        return x, y

    def _region_for_event(self, event: EarthquakeEvent) -> RegionSpec:
        if event.latitude is None or event.longitude is None:
            return JAPAN_REGION
        for spec in DETAILED_REGION_SPECS:
            if self._point_in_view(event.longitude, event.latitude, spec):
                return spec
        return self._generic_region(event)

    def _generic_region(self, event: EarthquakeEvent) -> RegionSpec:
        lon = event.longitude or 0.0
        lat = event.latitude or 0.0
        lon_span = 18.0
        lat_span = 14.0
        lon_min = max(-180.0, lon - lon_span / 2)
        lon_max = min(180.0, lon + lon_span / 2)
        lat_min = max(-80.0, lat - lat_span / 2)
        lat_max = min(80.0, lat + lat_span / 2)
        if lon_max - lon_min < 12.0:
            lon_max = min(180.0, lon_min + 12.0)
        if lat_max - lat_min < 10.0:
            lat_max = min(80.0, lat_min + 10.0)
        return RegionSpec(
            name='Regional locator',
            lon_min=lon_min,
            lon_max=lon_max,
            lat_min=lat_min,
            lat_max=lat_max,
            polygons=(),
            labels=(MapLabel('EPICENTER', lon, lat + 0.6, GENERIC_LABEL_COLOR),),
            water_labels=(),
        )

    def _accent_for_event(self, event: EarthquakeEvent) -> tuple[int, int, int]:
        alert_level = (event.alert_level or '').lower()
        magnitude = event.magnitude or 0.0
        if alert_level == 'red':
            return (255, 82, 82)
        if alert_level == 'orange':
            return (255, 161, 73)
        if magnitude >= 7.0:
            return (255, 110, 82)
        if magnitude >= 6.0:
            return (255, 145, 66)
        return (255, 196, 76)

    def _accent_glow_for_event(self, event: EarthquakeEvent) -> tuple[int, int, int]:
        alert_level = (event.alert_level or '').lower()
        if alert_level == 'red':
            return (255, 169, 148)
        if alert_level == 'orange':
            return (255, 203, 135)
        return (255, 215, 135)

    def _short_place(self, place: str) -> str:
        return place if len(place) <= 38 else f'{place[:35].rstrip()}...'

    def _rounded_panel(
        self,
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        fill: tuple[int, int, int],
        *,
        radius: int,
        outline: tuple[int, int, int] | None = None,
        width: int = 1,
    ) -> None:
        draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)

    def _wrap_text(
        self,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
        draw: ImageDraw.ImageDraw,
    ) -> list[str]:
        words = text.split()
        if not words:
            return ['']
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f'{current} {word}'
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _draw_text_block(
        self,
        draw: ImageDraw.ImageDraw,
        lines: list[str],
        *,
        left: int,
        top: int,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        fill: tuple[int, int, int],
        line_gap: int,
    ) -> int:
        current_top = top
        line_height = self._line_height(font)
        for line in lines:
            draw.text((left, current_top), line, fill=fill, font=font)
            current_top += line_height + line_gap
        return current_top - line_gap

    def _line_height(self, font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
        bbox = font.getbbox('Ag')
        return bbox[3] - bbox[1]

    def _truncate_text(
        self,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        *,
        max_width: int,
        draw: ImageDraw.ImageDraw,
    ) -> str:
        if draw.textlength(text, font=font) <= max_width:
            return text
        candidate = text
        while candidate and draw.textlength(candidate + '...', font=font) > max_width:
            candidate = candidate[:-1]
        return (candidate.rstrip() + '...') if candidate else '...'

    def _expand_box(self, box: tuple[int, int, int, int], padding: int) -> tuple[int, int, int, int]:
        left, top, right, bottom = box
        return (left - padding, top - padding, right + padding, bottom + padding)

    def _boxes_intersect(
        self,
        left_box: tuple[int, int, int, int],
        right_box: tuple[int, int, int, int],
    ) -> bool:
        return not (
            left_box[2] <= right_box[0]
            or left_box[0] >= right_box[2]
            or left_box[3] <= right_box[1]
            or left_box[1] >= right_box[3]
        )

    def _format_axis_label(self, value: float, positive_suffix: str, negative_suffix: str) -> str:
        suffix = positive_suffix if value >= 0 else negative_suffix
        return f'{abs(int(value))}{suffix}'

    def _format_coordinate(self, value: float, positive_suffix: str, negative_suffix: str) -> str:
        suffix = positive_suffix if value >= 0 else negative_suffix
        return f'{abs(value):.1f}{suffix}'

    def _compact_local_time(self, local_time: str) -> str:
        parts = local_time.split()
        if len(parts) >= 3:
            date_part, time_part, offset_part = parts[0], parts[1], parts[2]
            try:
                short_date = datetime.strptime(date_part, '%Y-%m-%d').strftime('%b %d')
            except ValueError:
                short_date = date_part
            return f'{short_date} {time_part} UTC{offset_part}'
        return local_time

    def _point_in_view(self, lon: float, lat: float, spec: RegionSpec) -> bool:
        return spec.lon_min <= lon <= spec.lon_max and spec.lat_min <= lat <= spec.lat_max

    def _polygon_intersects_view(self, polygon: tuple[tuple[float, float], ...], spec: RegionSpec) -> bool:
        lons = [lon for lon, _ in polygon]
        lats = [lat for _, lat in polygon]
        return not (
            max(lons) < spec.lon_min
            or min(lons) > spec.lon_max
            or max(lats) < spec.lat_min
            or min(lats) > spec.lat_max
        )

    def _location_indicator(self, event: EarthquakeEvent, spec: RegionSpec) -> str | None:
        if event.latitude is None or event.longitude is None or not spec.polygons:
            return None
        if self._point_on_land(event.longitude, event.latitude, spec.polygons):
            return None
        return "OFFSHORE"

    def _point_on_land(
        self,
        lon: float,
        lat: float,
        polygons: tuple[tuple[tuple[float, float], ...], ...] | list[tuple[tuple[float, float], ...]],
    ) -> bool:
        return any(self._point_in_polygon(lon, lat, polygon) for polygon in polygons)

    def _point_in_polygon(self, lon: float, lat: float, polygon: tuple[tuple[float, float], ...]) -> bool:
        inside = False
        point_count = len(polygon)
        if point_count < 3:
            return False

        lons = [point_lon for point_lon, _ in polygon]
        lats = [point_lat for _, point_lat in polygon]
        if lon < min(lons) or lon > max(lons) or lat < min(lats) or lat > max(lats):
            return False

        previous_lon, previous_lat = polygon[-1]
        for current_lon, current_lat in polygon:
            if self._point_on_segment(lon, lat, previous_lon, previous_lat, current_lon, current_lat):
                return True
            crosses_latitude = (current_lat > lat) != (previous_lat > lat)
            if crosses_latitude:
                intersection_lon = (
                    (previous_lon - current_lon) * (lat - current_lat) / (previous_lat - current_lat)
                ) + current_lon
                if lon < intersection_lon:
                    inside = not inside
            previous_lon, previous_lat = current_lon, current_lat

        return inside

    def _point_on_segment(
        self,
        lon: float,
        lat: float,
        start_lon: float,
        start_lat: float,
        end_lon: float,
        end_lat: float,
    ) -> bool:
        epsilon = 1e-9
        squared_length = (end_lon - start_lon) ** 2 + (end_lat - start_lat) ** 2
        if squared_length <= epsilon:
            return abs(lon - start_lon) <= epsilon and abs(lat - start_lat) <= epsilon
        cross = (lon - start_lon) * (end_lat - start_lat) - (lat - start_lat) * (end_lon - start_lon)
        if abs(cross) > epsilon:
            return False
        dot = (lon - start_lon) * (end_lon - start_lon) + (lat - start_lat) * (end_lat - start_lat)
        if dot < 0:
            return False
        return dot <= squared_length

    def _font(self, size: int, bold: bool = False, italic: bool = False):
        candidates: list[str] = []
        if bold and italic:
            candidates = [
                r'C:\Windows\Fonts\segoeuiz.ttf',
                r'C:\Windows\Fonts\arialbi.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf',
            ]
        elif bold:
            candidates = [
                r'C:\Windows\Fonts\segoeuib.ttf',
                r'C:\Windows\Fonts\arialbd.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            ]
        elif italic:
            candidates = [
                r'C:\Windows\Fonts\segoeuii.ttf',
                r'C:\Windows\Fonts\ariali.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf',
            ]
        else:
            candidates = [
                r'C:\Windows\Fonts\segoeui.ttf',
                r'C:\Windows\Fonts\arial.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            ]
        for path in candidates:
            if Path(path).exists():
                return ImageFont.truetype(path, size=size)
        return ImageFont.load_default()

    def _mono_font(self, size: int):
        candidates = [
            r'C:\Windows\Fonts\consola.ttf',
            r'C:\Windows\Fonts\lucon.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
        ]
        for path in candidates:
            if Path(path).exists():
                return ImageFont.truetype(path, size=size)
        return ImageFont.load_default()

    def _format_magnitude(self, magnitude: float | None) -> str:
        if magnitude is None:
            return 'unknown'
        return f'{magnitude:.1f}'
