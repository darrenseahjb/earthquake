from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from pathlib import Path


Polygon = tuple[tuple[float, float], ...]
RegionPolygons = dict[str, tuple[Polygon, ...]]


@lru_cache(maxsize=1)
def _load_region_polygons() -> RegionPolygons:
    raw_payload = _read_map_shapes_payload()
    payload = json.loads(raw_payload)
    region_polygons: RegionPolygons = {}
    for name, polygons in payload.items():
        typed_polygons: list[Polygon] = []
        for polygon in polygons:
            typed_polygons.append(tuple((float(lon), float(lat)) for lon, lat in polygon))
        region_polygons[str(name)] = tuple(typed_polygons)
    return region_polygons


def _read_map_shapes_payload() -> str:
    package_resource = files("earthquake_bot").joinpath("data/map_shapes.json")
    try:
        return package_resource.read_text(encoding="utf-8")
    except FileNotFoundError:
        pass

    candidate_paths = (
        Path(__file__).resolve().parent / "data" / "map_shapes.json",
        Path.cwd() / "src" / "earthquake_bot" / "data" / "map_shapes.json",
    )
    for candidate in candidate_paths:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")

    raise FileNotFoundError(
        "Could not find map_shapes.json in the installed package or source tree."
    )


REGION_POLYGONS = _load_region_polygons()

__all__ = ["REGION_POLYGONS"]
