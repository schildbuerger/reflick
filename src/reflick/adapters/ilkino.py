"""IL KINO, Nansenstr. 22, Neukölln.

The programme page (/movie-program) carries the whole programme, about a
month, as schema.org JSON-LD: an ItemList of ScreeningEvents (start time
with offset, duration, subtitle languages, kinoheld ticket link), each
pointing to a Movie (name, director, year as dateCreated, original language).

There's no language version as such; it follows from the subtitles: English
ones make it OmeU, German ones OmdU. "xx" means no subtitles, which can be a
dubbed or an original version, so it's left open.
"""

import json
import re
from datetime import datetime

from reflick.adapters.base import BERLIN, Adapter, Cache, Fetcher, Programme, clean
from reflick.models import Cinema, RawScreening

BASE_URL = "https://ilkino.de"
PROGRAMME_URL = f"{BASE_URL}/movie-program"
JSON_LD_RE = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?")
SUBTITLES = {("en",): "OmeU", ("de",): "OmdU", ("de", "en"): "OmdeU"}

CINEMA = Cinema(
    id="ilkino",
    name="Il Kino",
    address="Nansenstr. 22, 12047 Berlin",
    neighbourhood="Neukölln",
    website=f"{BASE_URL}/",
    lat=52.4917,
    lon=13.4330,  # from OpenStreetMap
)


def _items(data):
    """Every object in a JSON-LD document, through @graph and ItemList nesting."""
    if isinstance(data, list):
        for item in data:
            yield from _items(item)
    elif isinstance(data, dict):
        if "@graph" in data:
            yield from _items(data["@graph"])
        elif "itemListElement" in data:
            yield from _items(data["itemListElement"])
        else:
            yield data


def _runtime(duration: str | None) -> int | None:
    m = DURATION_RE.fullmatch(duration or "")
    if not m or not any(m.groups()):
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


def parse_programme(html: str) -> list[RawScreening]:
    objects = [obj for block in JSON_LD_RE.findall(html) for obj in _items(json.loads(block))]
    movies = {obj["@id"]: obj for obj in objects if obj.get("@type") == "Movie"}
    screenings = []
    for show in (obj for obj in objects if obj.get("@type") == "ScreeningEvent"):
        movie_id = (show.get("workPresented") or {}).get("@id", "")
        movie = movies.get(movie_id, {})
        director = clean(movie.get("director") or "")
        year = movie.get("dateCreated")
        subtitles = tuple(sorted(lang for lang in show.get("subtitleLanguage") or [] if lang and lang != "xx"))
        screenings.append(RawScreening(
            cinema_id=CINEMA.id,
            title=clean(show["name"]),
            start=datetime.fromisoformat(show["startDate"]).astimezone(BERLIN),
            source_url=movie_id.split("#")[0] or PROGRAMME_URL,
            ticket_url=(show.get("offers") or {}).get("url"),
            language=SUBTITLES.get(subtitles),
            year=int(year) if str(year or "").isdigit() else None,
            director=director if director and director != "(Unknown)" else None,
            runtime_min=_runtime(show.get("duration")),
        ))
    return screenings


class IlKinoAdapter(Adapter):
    id = "ilkino"

    def fetch(self, fetcher: Fetcher, cache: Cache | None = None) -> Programme:
        return Programme(cinemas=[CINEMA], screenings=parse_programme(fetcher.get(PROGRAMME_URL)))
