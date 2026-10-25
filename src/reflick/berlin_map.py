"""The site's map of Berlin, drawn as inline SVG at build time.

District outlines, rivers and the Ringbahn come from berlin_map.json (made by
scripts/make_berlin_map.py), so the page loads no map tiles or libraries and
contacts no one. Cinemas get pins; cinemas a few hundred metres apart (the
three at Zoo, Neues Off and Rollberg) share one, as separate pins would
overlap on a phone.
"""

import json
import math
from dataclasses import dataclass, field
from functools import cache
from importlib.resources import files

from reflick.models import Cinema

WIDTH = 1000.0  # SVG units across the drawn area of Berlin
MARGIN_KM = 1.5  # around the outermost cinemas
GROUP_WITHIN_M = 700  # pins are ~20 px wide; a phone shows ~27 px per km
# District names are 10 px text (~5.5 px a letter); they must fit on a 340 px wide phone map.
LABEL_CHAR_PX, LABEL_LINE_PX, NARROWEST_PX = 5.5, 14, 340
KM_PER_DEGREE_LAT = 111.32


@dataclass(frozen=True)
class Projection:
    """Equirectangular, which is accurate enough across a city: longitude is
    scaled by the cosine of Berlin's latitude. The page's script uses the same
    numbers to place "you are here" and to turn a tap back into a position."""

    west: float
    north: float
    scale: float  # SVG units per degree of latitude
    k: float  # cos(latitude): how much shorter a degree of longitude is

    def point(self, lon: float, lat: float) -> tuple[float, float]:
        return round((lon - self.west) * self.k * self.scale, 1), round((self.north - lat) * self.scale, 1)

    def path(self, points: list[list[float]], closed: bool = False) -> str:
        """SVG path data; points after the first are implicit line-tos."""
        coordinates = (self.point(lon, lat) for lon, lat in points)
        return "M" + " ".join(f"{x:g},{y:g}" for x, y in coordinates) + ("Z" if closed else "")


@dataclass(frozen=True)
class District:
    name: str
    path: str
    label: tuple[float, float]


@dataclass(frozen=True)
class BerlinMap:
    projection: Projection
    districts: list[District]
    water: str
    ring: str


@cache
def berlin_map() -> BerlinMap:
    data = json.loads((files("reflick") / "berlin_map.json").read_text(encoding="utf-8"))
    points = [p for d in data["districts"] for ring in d["rings"] for p in ring]
    west, east = min(p[0] for p in points), max(p[0] for p in points)
    south, north = min(p[1] for p in points), max(p[1] for p in points)
    k = math.cos(math.radians((north + south) / 2))
    projection = Projection(west, north, WIDTH / ((east - west) * k), k)
    return BerlinMap(
        projection=projection,
        districts=[
            District(d["name"], "".join(projection.path(r, closed=True) for r in d["rings"]),
                     projection.point(*d["label"]))
            for d in data["districts"]
        ],
        water="".join(projection.path(line) for line in data["water"]),
        ring=projection.path(data["ring"], closed=True),
    )


def distance_m(a: Cinema, b: Cinema) -> float:
    dx = (a.lon - b.lon) * math.cos(math.radians(a.lat))
    return math.hypot(dx, a.lat - b.lat) * KM_PER_DEGREE_LAT * 1000


@dataclass
class Pin:
    """One pin: a cinema, or a few next to each other."""

    id: str  # the first cinema's id
    x: float
    y: float
    cinemas: list[Cinema] = field(default_factory=list)

    @property
    def name(self) -> str:
        return ", ".join(c.name for c in self.cinemas)


def pins(cinemas: list[Cinema], projection: Projection) -> list[Pin]:
    """Pins for the cinemas that have coordinates, neighbours sharing one."""
    groups: list[list[Cinema]] = []
    for cinema in sorted((c for c in cinemas if c.lat is not None), key=lambda c: c.name.casefold()):
        group = next((g for g in groups if distance_m(g[0], cinema) <= GROUP_WITHIN_M), None)
        if group:
            group.append(cinema)
        else:
            groups.append([cinema])
    found = []
    for group in groups:
        lon = sum(c.lon for c in group) / len(group)
        lat = sum(c.lat for c in group) / len(group)
        found.append(Pin(group[0].id, *projection.point(lon, lat), group))
    return found


def view_box(cinemas: list[Cinema], projection: Projection) -> tuple[float, float, float, float]:
    """The part of the map around all the given cinemas (x, y, width, height)."""
    located = [c for c in cinemas if c.lat is not None]
    if not located:
        raise ValueError("no cinema has coordinates")
    xs, ys = zip(*(projection.point(c.lon, c.lat) for c in located), strict=True)
    margin = MARGIN_KM / KM_PER_DEGREE_LAT * projection.scale
    x, y = min(xs) - margin, min(ys) - margin
    return round(x, 1), round(y, 1), round(max(xs) - x + margin, 1), round(max(ys) - y + margin, 1)


def labelled(districts: list[District], box: tuple[float, float, float, float]) -> list[District]:
    """Districts whose centre is in view, with the label moved sideways where
    needed so the name isn't cut off at the edge, even on a narrow phone."""
    x, y, w, h = box
    units_per_px = w / NARROWEST_PX
    half_height = LABEL_LINE_PX / 2 * units_per_px
    shown = []
    for d in districts:
        half_width = min(len(d.name) * LABEL_CHAR_PX / 2 * units_per_px, w / 2)
        lx, ly = d.label
        if x <= lx <= x + w and y + half_height <= ly <= y + h - half_height:
            lx = min(max(lx, x + half_width), x + w - half_width)
            shown.append(District(d.name, d.path, (round(lx, 1), ly)))
    return shown
