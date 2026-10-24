"""Static site: renders upcoming revivals into one HTML page and an iCal feed.

Output layout:
    index.html   all upcoming revivals across cinemas by day, with filters
    reflick.ics  calendar feed of all listed screenings
"""

import hashlib
import itertools
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from jinja2 import Environment, PackageLoader, select_autoescape

from reflick import db
from reflick.models import Cinema, RawScreening
from reflick.revival import is_revival, revival_labels
from reflick.titles import display_title, split_addons

BERLIN = ZoneInfo("Europe/Berlin")
DEFAULT_RUNTIME = timedelta(minutes=120)
NIGHT_CUTOFF = timedelta(hours=5)
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


@dataclass
class Item:
    """One screening as shown on the site."""

    id: int
    screening: RawScreening
    cinema: Cinema
    start: datetime  # in Europe/Berlin
    title: str  # film title without cinema add-ons, verified on OMDb if matched
    labels: list[str]  # series/re-release labels and title add-ons, shown as badges
    genres: list[str]  # from OMDb, empty if the film wasn't matched
    imdb_id: str | None = None  # from OMDb, if matched

    @property
    def letterboxd_url(self) -> str | None:
        """Letterboxd's IMDb-id address, which redirects to the film's page there."""
        return f"https://letterboxd.com/imdb/{self.imdb_id}/" if self.imdb_id else None

    @property
    def programme_day(self) -> date:
        """Late shows belong to the evening before, as in cinema programmes."""
        return (self.start - NIGHT_CUTOFF).date()

    @property
    def time_label(self) -> str:
        hour = self.start.hour
        if self.programme_day < self.start.date():
            hour += 24  # e.g. 00:30 on Sunday is shown as 24:30 on Saturday
        return f"{hour:02d}:{self.start.minute:02d}"

    @property
    def facts(self) -> str:
        s = self.screening
        parts = [s.country, str(s.year) if s.year else None, s.director]
        if s.runtime_min:
            parts.append(f"{s.runtime_min} min")
        return " · ".join(p for p in parts if p)


def by_day(items: list[Item]) -> list[tuple[date, list[Item]]]:
    """Group items that are already in start order by programme day."""
    return [
        (day, list(group))
        for day, group in itertools.groupby(items, key=lambda i: i.programme_day)
    ]


def day_name(day: date) -> str:
    """'Saturday, 24. October'."""
    return f"{WEEKDAYS[day.weekday()]}, {day.day}. {MONTHS[day.month - 1]}"


def short_day(day: date) -> str:
    """'Sat 24. Oct', for the date strip."""
    return f"{WEEKDAYS[day.weekday()][:3]} {day.day}. {MONTHS[day.month - 1][:3]}"


def maps_url(cinema: Cinema) -> str:
    """Google Maps search for the cinema (Maps URLs API, no key needed)."""
    query = urlencode({"api": 1, "query": f"{cinema.name}, {cinema.address}"})
    return f"https://www.google.com/maps/search/?{query}"


def make_item(
    i: int, s: RawScreening, cinemas: dict[str, Cinema], films: dict[tuple[str, int], db.FilmInfo]
) -> Item:
    base_title, addons = split_addons(s.title)
    info = films.get((db.title_key(s.title), s.year)) if s.year else None
    return Item(
        id=i,
        screening=s,
        cinema=cinemas[s.cinema_id],
        start=s.start.astimezone(BERLIN),
        title=display_title(base_title, info.title if info else None),
        labels=[*revival_labels(s), *addons],
        genres=info.genres if info else [],
        imdb_id=info.imdb_id if info else None,
    )


def collect(
    screenings: list[RawScreening],
    cinemas: dict[str, Cinema],
    films: dict[tuple[str, int], db.FilmInfo],
    now: datetime,
) -> list[Item]:
    """Upcoming revivals across all cinemas, in start order."""
    upcoming = sorted(
        (s for s in screenings if s.start >= now and is_revival(s, now.date())),
        key=lambda s: (s.start, s.title),
    )
    return [make_item(i, s, cinemas, films) for i, s in enumerate(upcoming)]


def _ics_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    )


def _ics_fold(line: str) -> str:
    """Fold lines longer than 75 octets, as RFC 5545 requires."""
    out, current = [], ""
    for char in line:
        if len((current + char).encode()) > 75:
            out.append(current)
            current = " " + char
        else:
            current += char
    out.append(current)
    return "\r\n".join(out)


def _ics_time(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def render_ics(items: list[Item], now: datetime) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//reflick//revival screenings Berlin//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:reflick – revival screenings in Berlin",
    ]
    for item in items:
        s = item.screening
        runtime = timedelta(minutes=s.runtime_min) if s.runtime_min else DEFAULT_RUNTIME
        uid_source = f"{s.cinema_id}|{s.start.isoformat()}|{s.title}"
        title = f"{item.title} ({s.year})" if s.year else item.title
        description = " · ".join(p for p in (item.facts, s.language, *item.labels) if p)
        lines += [
            "BEGIN:VEVENT",
            f"UID:{hashlib.sha1(uid_source.encode()).hexdigest()}@reflick",
            f"DTSTAMP:{_ics_time(now)}",
            f"DTSTART:{_ics_time(s.start)}",
            f"DTEND:{_ics_time(s.start + runtime)}",
            f"SUMMARY:{_ics_escape(title)}",
            f"LOCATION:{_ics_escape(f'{item.cinema.name}, {item.cinema.address}')}",
            f"DESCRIPTION:{_ics_escape(description)}",
            f"URL:{s.source_url}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_ics_fold(line) for line in lines) + "\r\n"


def _environment() -> Environment:
    env = Environment(
        loader=PackageLoader("reflick", "templates"),
        autoescape=select_autoescape(),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["day_name"] = day_name
    env.filters["short_day"] = short_day
    env.filters["maps_url"] = maps_url
    return env


def _pairs(values) -> list[tuple[str, str]]:
    """Distinct non-empty values, sorted, as (value, text) filter options."""
    return [(v, v) for v in sorted({v for v in values if v}, key=str.casefold)]


def build(conn: sqlite3.Connection, out_dir: Path, now: datetime | None = None) -> int:
    """Write the site to out_dir. Returns the number of screenings listed."""
    now = now or datetime.now(BERLIN)
    cinemas = db.cinemas(conn)
    items = collect(db.latest_screenings(conn), cinemas, db.film_info(conn), now)
    updated = db.last_update(conn)
    out_dir.mkdir(parents=True, exist_ok=True)

    listed_cinemas = sorted({i.cinema for i in items}, key=lambda c: c.name.casefold())
    # Filter choices as (value, text) pairs; only values that occur are offered.
    options = {
        "cinemas": [(c.id, c.name) for c in listed_cinemas],
        "districts": _pairs(i.cinema.neighbourhood for i in items),
        "languages": _pairs(i.screening.language for i in items),
        "genres": _pairs(g for i in items for g in i.genres),
    }
    rows = [
        {
            "id": i.id,
            "day": i.programme_day.isoformat(),
            "cinema": i.cinema.id,
            "district": i.cinema.neighbourhood,
            "language": i.screening.language or "",
            "genres": i.genres,
            "text": " ".join(
                # Both titles, so "Gold Rush" and "Orchester" both find the Chaplin show.
                filter(None, (i.title, i.screening.title, i.screening.director, i.screening.series))
            ).casefold(),
        }
        for i in items
    ]
    index = _environment().get_template("index.html").render(
        days=by_day(items),
        options=options,
        cinema_names={c.id: c.name for c in listed_cinemas},
        rows=rows,
        cinemas=listed_cinemas,
        updated=updated.astimezone(BERLIN) if updated else None,
    )
    (out_dir / "index.html").write_text(index, encoding="utf-8")
    (out_dir / "reflick.ics").write_text(render_ics(items, now), encoding="utf-8", newline="")
    return len(items)
