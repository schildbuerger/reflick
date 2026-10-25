"""Brotfabrik Kino, Caligariplatz 1, Weißensee.

The Brotfabrik is a venue with a stage and a gallery too; its WordPress site
lists everything through The Events Calendar, whose REST API
(/wp-json/tribe/events/v1/events) returns one event per screening with a
full start time and the ticket link. Only the "kino" category is read. The
credits are a line in the description:

    D 1932 | 71 min | Spielfilm | R: Slatan Dudow
    Solidarność Według Kobiet | Polen 2014 | 103 min | Regie: Marta Dzido, Piotr Śliwowski | OmU

The API's own link to the next page drops the category filter, so page
URLs are built here; the link only tells whether there is a next page.
"""

import html
import json
import re
from datetime import datetime, time, timedelta

from reflick.adapters.base import (
    BERLIN,
    Adapter,
    Cache,
    Fetcher,
    Programme,
    berlin_today,
    clean,
    fetch_pages,
    language_code,
)
from reflick.models import Cinema, RawScreening

BASE_URL = "https://brotfabrik-berlin.de"
EVENTS_URL = (
    f"{BASE_URL}/wp-json/tribe/events/v1/events"
    "?categories=kino&per_page=50&start_date={start}&end_date={end}&page={page}"
)
DAYS_AHEAD = 90

CINEMA = Cinema(
    id="brotfabrik",
    name="Brotfabrik Kino",
    address="Caligariplatz 1, 13086 Berlin",
    neighbourhood="Weißensee",
    website=f"{BASE_URL}/kino/",
    lat=52.5526,
    lon=13.4306,  # from OpenStreetMap
)

# "D 1932", or "D 1925/26" (the first year counts).
COUNTRY_YEAR_RE = re.compile(r"(.+?)\s+((?:18|19|20)\d{2})(?:/\d{2,4})?")
DIRECTOR_RE = re.compile(r"(?:R|Regie):\s*(.+)")
LANGUAGE_RE = re.compile(r"(Om\w*U|OV|OF|DF)\b")


def _text(value: str) -> str:
    """Unescape HTML entities and drop soft hyphens and no-break spaces."""
    return clean(html.unescape(value).replace("\xad", ""))


def credits_line(description: str) -> str | None:
    """The 'D 1932 | 71 min | Spielfilm | R: ...' line of a description. It's
    sometimes broken after 'R:' or a '|', so such lines run on into the next."""
    lines: list[str] = []
    for line in filter(None, (_text(x) for x in re.split(r"<[^>]+>|\n", description))):
        if lines and lines[-1].endswith(("|", ":")):
            lines[-1] += " " + line
        else:
            lines.append(line)
    for line in lines:
        if "|" in line and COUNTRY_YEAR_RE.search(line) and re.search(r"\bmin\b|\bR(?:egie)?:", line):
            return line
    return None


def parse_credits(line: str) -> dict:
    """Year, country, original title, runtime, director and language from a
    credits line. Notes after the director's name ('R: Ernst Lubitsch,
    deutsche Zwischentitel') count as language notes."""
    segments = [s.strip() for s in line.split("|") if s.strip()]
    facts: dict = {}
    notes: list[str] = []
    for i, segment in enumerate(segments):
        if "year" not in facts and (m := COUNTRY_YEAR_RE.fullmatch(segment)):
            facts["country"], facts["year"] = m.group(1), int(m.group(2))
            if i:
                facts["original_title"] = " | ".join(segments[:i])
        elif m := DIRECTOR_RE.match(segment):
            # Names are separated by commas; a lowercase part is a note.
            names = [p.strip() for p in m.group(1).split(",")]
            facts["director"] = ", ".join(p for p in names if not p[:1].islower())
            notes += [p for p in names if p[:1].islower()]
        elif m := LANGUAGE_RE.match(segment):
            facts["language"] = m.group(1)
        elif "titel" in segment:  # "englische Untertitel"
            notes.append(segment)
    if runtime := re.search(r"(\d+)\s*min\b", line):
        facts["runtime_min"] = int(runtime.group(1))
    if "language" not in facts and notes:
        facts["language"] = ", ".join(notes)
    return facts


def parse_event(event: dict) -> RawScreening | None:
    if not any(c.get("slug") == "kino" for c in event.get("categories", [])):
        return None
    line = credits_line(event.get("description") or "")
    facts = parse_credits(line) if line else {}
    return RawScreening(
        cinema_id=CINEMA.id,
        title=_text(event["title"]),
        start=datetime.fromisoformat(event["start_date"]).replace(tzinfo=BERLIN),
        source_url=event["url"],
        ticket_url=event.get("website") or None,
        language=language_code(facts.get("language")),
        year=facts.get("year"),
        country=facts.get("country"),
        director=facts.get("director") or None,
        runtime_min=facts.get("runtime_min"),
        original_title=facts.get("original_title"),
    )


def parse_page(text: str) -> tuple[list[RawScreening], bool]:
    """One page of the events API: its screenings, and whether it's the last
    page (only earlier pages link to a next one)."""
    data = json.loads(text)
    events = (parse_event(e) for e in data.get("events", []))
    return [s for s in events if s], "next_rest_url" not in data


class BrotfabrikAdapter(Adapter):
    id = "brotfabrik"

    def fetch(self, fetcher: Fetcher, cache: Cache | None = None) -> Programme:
        today = berlin_today()
        end = today + timedelta(days=DAYS_AHEAD)
        until = datetime.combine(end, time(), tzinfo=BERLIN)
        page_url = EVENTS_URL.format(start=today.isoformat(), end=end.isoformat(), page="{}")
        screenings = fetch_pages(fetcher, page_url.format, parse_page, until)
        # Pages can overlap when the programme changes while they're read.
        unique = {(s.source_url, s.start): s for s in screenings}
        return Programme(cinemas=[CINEMA], screenings=list(unique.values()))
