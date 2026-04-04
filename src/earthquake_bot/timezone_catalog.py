from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo


REGION_LABELS: dict[str, str] = {
    "africa": "Africa",
    "americas": "Americas",
    "asia": "Asia",
    "europe": "Europe",
    "oceania": "Oceania",
    "atlantic": "Atlantic",
    "indian": "Indian Ocean",
    "antarctica": "Antarctica",
    "arctic": "Arctic",
}

REGION_ORDER = list(REGION_LABELS)

ZONE_ROOT_TO_REGION: dict[str, str] = {
    "Africa": "africa",
    "America": "americas",
    "Asia": "asia",
    "Europe": "europe",
    "Australia": "oceania",
    "Pacific": "oceania",
    "Atlantic": "atlantic",
    "Indian": "indian",
    "Antarctica": "antarctica",
    "Arctic": "arctic",
}


@dataclass(frozen=True, slots=True)
class CountryTimezones:
    code: str
    name: str
    region_slug: str
    timezones: tuple[str, ...]
    comments: tuple[str, ...]
    offset_label: str


def list_regions() -> list[tuple[str, str]]:
    catalog = _catalog()
    return [(slug, REGION_LABELS[slug]) for slug in REGION_ORDER if catalog.get(slug)]


def countries_for_region(region_slug: str) -> list[CountryTimezones]:
    return list(_catalog().get(region_slug, ()))


def get_country(code: str) -> CountryTimezones | None:
    return _countries_by_code().get(code.upper())


def country_button_label(country: CountryTimezones) -> str:
    return f"{country.name} ({country.offset_label})"


def timezone_label(country: CountryTimezones, index: int) -> str:
    zone_name = country.timezones[index]
    comment = country.comments[index]
    city = comment or zone_name.rsplit("/", 1)[-1].replace("_", " ")
    return f"{city} ({gmt_label_for_timezone(zone_name)})"


def gmt_label_for_timezone(zone_name: str, when: datetime | None = None) -> str:
    current = when or datetime.now(timezone.utc)
    zone = ZoneInfo(zone_name)
    offset = current.astimezone(zone).utcoffset()
    return _format_offset(offset)


def region_label(region_slug: str) -> str:
    return REGION_LABELS.get(region_slug, region_slug.title())


@lru_cache(maxsize=1)
def _catalog() -> dict[str, tuple[CountryTimezones, ...]]:
    countries = list(_countries_by_code().values())
    grouped: dict[str, list[CountryTimezones]] = defaultdict(list)
    for country in countries:
        grouped[country.region_slug].append(country)

    return {
        slug: tuple(sorted(items, key=lambda item: item.name.casefold()))
        for slug, items in grouped.items()
    }


@lru_cache(maxsize=1)
def _countries_by_code() -> dict[str, CountryTimezones]:
    country_names = _load_country_names()
    timezones_by_country: dict[str, list[str]] = defaultdict(list)
    comments_by_country: dict[str, list[str]] = defaultdict(list)

    for code, zone_name, comment in _load_zone_rows():
        timezones_by_country[code].append(zone_name)
        comments_by_country[code].append(comment)

    countries: dict[str, CountryTimezones] = {}
    for code, timezones in timezones_by_country.items():
        comments = comments_by_country[code]
        country_name = country_names.get(code, code)
        region_slug = _region_for_timezones(timezones)
        countries[code] = CountryTimezones(
            code=code,
            name=country_name,
            region_slug=region_slug,
            timezones=tuple(timezones),
            comments=tuple(comments),
            offset_label=_country_offset_label(timezones),
        )

    return countries


def _load_country_names() -> dict[str, str]:
    rows = _read_zoneinfo_file("iso3166.tab").splitlines()
    country_names: dict[str, str] = {}
    for raw_line in rows:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        code, name = line.split("\t", 1)
        country_names[code] = name
    return country_names


def _load_zone_rows() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for raw_line in _read_zoneinfo_file("zone.tab").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        code = parts[0].strip().upper()
        zone_name = parts[2].strip()
        comment = parts[3].strip() if len(parts) > 3 else ""
        rows.append((code, zone_name, comment))
    return rows


def _read_zoneinfo_file(filename: str) -> str:
    try:
        return files("tzdata.zoneinfo").joinpath(filename).read_text(encoding="utf-8")
    except ModuleNotFoundError:
        fallback = Path(__file__).resolve().parents[2] / ".venv" / "Lib" / "site-packages" / "tzdata" / "zoneinfo"
        return (fallback / filename).read_text(encoding="utf-8")


def _region_for_timezones(timezones: Iterable[str]) -> str:
    slugs = [ZONE_ROOT_TO_REGION.get(zone.split("/", 1)[0], "asia") for zone in timezones]
    return Counter(slugs).most_common(1)[0][0]


def _country_offset_label(timezones: Iterable[str]) -> str:
    unique_offsets = sorted({_offset_minutes(zone_name) for zone_name in timezones})
    labels = [_format_offset(timedelta(minutes=minutes)) for minutes in unique_offsets]
    if len(labels) == 1:
        return labels[0]
    if len(labels) <= 3:
        return " / ".join(labels)
    return f"{labels[0]} to {labels[-1]}"


def _format_offset(offset: timedelta | None) -> str:
    if offset is None:
        return "GMT"

    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    absolute_minutes = abs(total_minutes)
    hours, minutes = divmod(absolute_minutes, 60)
    if minutes == 0:
        return f"GMT{sign}{hours:02d}"
    return f"GMT{sign}{hours:02d}:{minutes:02d}"


def _offset_minutes(zone_name: str) -> int:
    current = datetime.now(timezone.utc)
    offset = current.astimezone(ZoneInfo(zone_name)).utcoffset()
    if offset is None:
        return 0
    return int(offset.total_seconds() // 60)
