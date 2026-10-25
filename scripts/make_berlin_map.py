"""Make src/reflick/berlin_map.json, the outline data the site's map is drawn from.

Run by hand when the map should change (it isn't part of the daily build):

    .venv/bin/python scripts/make_berlin_map.py

Sources, read once here so the site itself contacts no one:
- District boundaries: ALKIS Berlin Bezirke from Berlin's open data portal,
  Datenlizenz Deutschland – Zero 2.0 (no attribution required).
- Spree, Havel and the Ringbahn (S41's stations, in order): OpenStreetMap via
  the Overpass API, © OpenStreetMap contributors, ODbL. The site credits it.

Lines are simplified (Douglas-Peucker) to keep the page small: the map only
needs to show roughly where a cinema is.
"""

import json
import math
import time
from pathlib import Path

import httpx

DISTRICTS_URL = "https://tsb-opendata.s3.eu-central-1.amazonaws.com/bezirksgrenzen/bezirksgrenzen.geojson"
OVERPASS_URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
BBOX = "52.33,13.08,52.68,13.77"  # south, west, north, east: all of Berlin
WATER_QUERY = f'[out:json][timeout:90];way["waterway"="river"]["name"~"^(Spree|Havel)$"]({BBOX});out geom;'
RING_QUERY = '[out:json][timeout:90];relation["route"="light_rail"]["ref"="S41"];out geom;'
OUT = Path(__file__).parent.parent / "src" / "reflick" / "berlin_map.json"
USER_AGENT = "reflick/0.1 (+https://github.com/schildbuerger/reflick; one-off map data download)"
# Simplification tolerance in degrees of latitude (~0.0007° = 80 m).
TOLERANCE = 0.0007


def simplify(points: list[tuple[float, float]], tolerance: float = TOLERANCE) -> list[tuple[float, float]]:
    """Douglas-Peucker on (lon, lat) points, with longitude scaled to Berlin's latitude."""
    if len(points) < 3:
        return points
    k = math.cos(math.radians(52.5))

    def distance(p, a, b):
        (px, py), (ax, ay), (bx, by) = [(x * k, y) for x, y in (p, a, b)]
        dx, dy = bx - ax, by - ay
        if dx == dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - ax - t * dx, py - ay - t * dy)

    index, furthest = 0, 0.0
    for i in range(1, len(points) - 1):
        if (d := distance(points[i], points[0], points[-1])) > furthest:
            index, furthest = i, d
    if furthest <= tolerance:
        return [points[0], points[-1]]
    return simplify(points[: index + 1], tolerance)[:-1] + simplify(points[index:], tolerance)


def rounded(points) -> list[list[float]]:
    return [[round(lon, 4), round(lat, 4)] for lon, lat in points]


def label_point(ring: list[tuple[float, float]]) -> list[float]:
    """The polygon's centroid, where its name goes."""
    area = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1], strict=True):
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    return [round(cx / (3 * area), 4), round(cy / (3 * area), 4)]


def overpass(client: httpx.Client, query: str) -> list[dict]:
    """A query's elements. Public Overpass servers are often busy: retry with growing pauses."""
    for attempt in range(6):
        url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
        try:
            response = client.post(url, data={"data": query}, timeout=120)
            if response.status_code == 200:
                return response.json()["elements"]
            print(f"{url}: HTTP {response.status_code}")
        except httpx.HTTPError as exc:
            print(f"{url}: {exc!r}")
        time.sleep(10 * 2**attempt)
    raise SystemExit("Overpass is unavailable; try again later")


def districts(client: httpx.Client) -> list[dict]:
    found = []
    for feature in client.get(DISTRICTS_URL, timeout=60).json()["features"]:
        geometry = feature["geometry"]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        outers = [[tuple(p) for p in polygon[0]] for polygon in polygons]  # no holes at this scale
        largest = max(outers, key=len)
        found.append({
            "name": feature["properties"]["Gemeinde_name"],
            "rings": [rounded(simplify(ring)) for ring in outers if len(ring) > 20],
            "label": label_point(largest),
        })
    return sorted(found, key=lambda d: d["name"])


def water(client: httpx.Client) -> list[list[list[float]]]:
    lines = []
    for way in overpass(client, WATER_QUERY):
        line = simplify([(p["lon"], p["lat"]) for p in way["geometry"]])
        if len(line) >= 2:
            lines.append(rounded(line))
    return lines


def ring(client: httpx.Client) -> list[list[float]]:
    """S41's stations in running order, which outline the Ringbahn closely enough."""
    relation = next(iter(overpass(client, RING_QUERY)))
    stops = [(m["lon"], m["lat"]) for m in relation["members"] if m["type"] == "node" and m["role"].startswith("stop")]
    return rounded(dict.fromkeys(stops))  # each station once; the ring is drawn closed


def main() -> None:
    with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
        data = {
            "sources": "Districts: ALKIS Berlin (dl-de/zero-2-0)."
            " Rivers, Ringbahn: © OpenStreetMap contributors (ODbL).",
            "districts": districts(client),
            "water": water(client),
            "ring": ring(client),
        }
    OUT.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    points = sum(len(r) for d in data["districts"] for r in d["rings"]) + sum(map(len, data["water"]))
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, {points} points, {len(data['ring'])} ring stations)")


if __name__ == "__main__":
    main()
