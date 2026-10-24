"""Yorck Kinogruppe: 14 cinemas, one programme.

yorck.de is a Next.js site: every page embeds its data as JSON in
`<script id="__NEXT_DATA__">`. The adapter reads:

- /kinos: the cinemas (name, slug, address, district).
- /filme: every film with all its sessions across the cinemas, plus the
  "specials" (series, festivals, talks) with theirs. A session has a start
  time with UTC offset, the cinema's name and formats (DF, OmU, OV, Sneak ...).
  A film's `releaseDate` is its German release, not necessarily the original.
- /filme/<slug>: credits (year, director, original title, countries). Only
  read for revival candidates, and cached for a month.
- /specials/<slug>: for film series whose sessions aren't listed under any
  film, to find out which film each session shows.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import httpx

from reflick.adapters.base import Adapter, Cache, Fetcher, Programme, clean
from reflick.models import Cinema, RawScreening
from reflick.revival import MIN_AGE_YEARS

BASE_URL = "https://www.yorck.de"
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)

LANGUAGES = {"DF", "OmU", "OmeU", "OmdU", "OV", "OF"}
SKIP_FORMATS = {"Sneak"}  # surprise previews: the film is unknown
# Specials that are readings, stage shows or (mostly short-film) festivals.
SKIP_SPECIAL_CATEGORIES = {"Lesung", "Bühne", "Festival"}
SERIES_TYPES = {"Film Series", "Film Special"}
FILM_CACHE = "yorck-film"
FILM_CACHE_AGE = timedelta(days=30)


def next_data(html: str) -> dict:
    """The page's own data: `props.pageProps` of __NEXT_DATA__."""
    m = NEXT_DATA_RE.search(html)
    if m is None:
        raise ValueError("no __NEXT_DATA__ on page")
    return json.loads(m.group(1))["props"]["pageProps"]


def _fields(obj) -> dict:
    """Contentful entries wrap their data in 'fields'."""
    return obj.get("fields", obj) if isinstance(obj, dict) else {}


def _year(value: str | None) -> int | None:
    return int(value[:4]) if value and value[:4].isdigit() else None


def parse_cinemas(page: dict) -> dict[str, Cinema]:
    """Cinemas from /kinos, keyed by the name sessions use (casefolded)."""
    cinemas = {}
    for entry in page.get("cinemas") or []:
        f = _fields(entry)
        if f.get("showOnCinemaListingPage") is False:
            continue
        name = clean(f["name"])  # e.g. "Blauer Stern " has a trailing space
        cinemas[name.casefold()] = Cinema(
            id=f"yorck-{f['slug']}",
            name=name,
            address=clean(f.get("address") or ""),
            neighbourhood=clean(f.get("district") or ""),
            website=f"{BASE_URL}/kinos/{f['slug']}",
        )
    return cinemas


@dataclass
class Session:
    id: str
    start: datetime
    cinema_name: str
    formats: list[str]
    film_slug: str
    title: str
    runtime: int | None
    release_year: int | None  # German release
    series: str | None = None
    categories: list[str] = field(default_factory=list)

    @property
    def is_sneak(self) -> bool:
        """Surprise preview: the film is unknown. Not always tagged as a format."""
        return bool(SKIP_FORMATS & set(self.formats)) or "sneak" in self.title.casefold()

    def is_candidate(self, today: date) -> bool:
        """Might be a revival, so worth reading the film's credits."""
        if self.release_year is None or today.year - self.release_year >= MIN_AGE_YEARS:
            return True
        return any("klassiker" in c.casefold() for c in self.categories)


def _session(raw: dict, film: dict) -> Session:
    f = _fields(raw)
    return Session(
        id=f.get("sessionId") or raw["sys"]["id"],
        start=datetime.fromisoformat(f["startTime"]),
        cinema_name=clean(_fields(f.get("cinema")).get("name", "")),
        formats=list(f.get("formats") or []),
        film_slug=film["slug"],
        title=clean(film["title"]),
        runtime=film.get("runtime"),
        release_year=_year(film.get("releaseDate")),
    )


def _apply_special(session: Session, special: dict) -> None:
    if category := special.get("category"):
        session.categories.append(category)
    if special.get("type") in SERIES_TYPES or category in {"Filmreihe", "Klassiker"}:
        session.series = session.series or clean(special["title"])


def parse_listing(page: dict) -> tuple[dict[str, Session], list[str]]:
    """Sessions from /filme by id, and slugs of specials with sessions of their own."""
    sessions: dict[str, Session] = {}
    for entry in page.get("films") or []:
        film = _fields(entry)
        for raw in film.get("sessions") or []:
            s = _session(raw, film)
            sessions[s.id] = s
    pending = []
    for entry in page.get("specials") or []:
        special = _fields(entry)
        for raw in special.get("sessions") or []:
            sid = raw["sys"]["id"]
            if sid in sessions:
                _apply_special(sessions[sid], special)
            elif special.get("category") not in SKIP_SPECIAL_CATEGORIES and special["slug"] not in pending:
                pending.append(special["slug"])
    return sessions, pending


def parse_special_page(page: dict) -> list[Session]:
    """Sessions of a special, each with the film it shows."""
    special = _fields(page.get("special"))
    found = []
    for raw in page.get("sessions") or []:
        film = _fields(_fields(raw).get("film"))
        if not film.get("slug"):
            continue
        s = _session(raw, film)
        _apply_special(s, special)
        found.append(s)
    return found


def parse_film_page(page: dict) -> dict:
    """Credits from /filme/<slug>. Under load the site sometimes serves the
    page without its film data; that raises, so it isn't cached as empty."""
    f = _fields(page.get("film"))
    if not f.get("title"):
        raise ValueError("film page without film data")
    year = f.get("year")
    return {
        "year": int(year) if str(year or "").isdigit() else None,
        "director": clean(f.get("director") or "") or None,
        "original_title": clean(f.get("originalTitle") or "") or None,
        "country": ", ".join(f.get("countries") or []) or None,
    }


def to_screening(s: Session, cinema: Cinema, credits: dict) -> RawScreening:
    language = next((f for f in s.formats if f in LANGUAGES), None)
    original = credits.get("original_title")
    return RawScreening(
        cinema_id=cinema.id,
        title=s.title,
        start=s.start,
        source_url=f"{BASE_URL}/filme/{s.film_slug}",
        language=language,
        series=s.series,
        tags=[f for f in s.formats if f not in LANGUAGES] + s.categories,
        year=credits.get("year") or s.release_year,
        country=credits.get("country"),
        director=credits.get("director"),
        runtime_min=s.runtime,
        original_title=original if original and original != s.title else None,
    )


class YorckAdapter(Adapter):
    id = "yorck"

    def fetch(self, fetcher: Fetcher, cache: Cache | None = None) -> Programme:
        cache = cache or Cache()
        today = date.today()
        warnings: list[str] = []

        cinemas = parse_cinemas(next_data(fetcher.get(f"{BASE_URL}/kinos")))
        sessions, pending = parse_listing(next_data(fetcher.get(f"{BASE_URL}/filme")))
        for slug in pending:
            try:
                page = next_data(fetcher.get(f"{BASE_URL}/specials/{slug}"))
            except (httpx.HTTPError, ValueError) as exc:
                warnings.append(f"special {slug}: {exc!r}")
                continue
            for s in parse_special_page(page):
                sessions.setdefault(s.id, s)

        credits: dict[str, dict] = {}
        screenings = []
        unknown_cinemas = set()
        for s in sorted(sessions.values(), key=lambda s: s.start):
            if s.is_sneak:
                continue
            cinema = cinemas.get(s.cinema_name.casefold())
            if cinema is None:
                unknown_cinemas.add(s.cinema_name)
                continue
            if s.is_candidate(today) and s.film_slug not in credits:
                credits[s.film_slug] = self._credits(fetcher, cache, s.film_slug, warnings)
            screenings.append(to_screening(s, cinema, credits.get(s.film_slug, {})))

        warnings += [f"unknown cinema in programme: {name!r}" for name in sorted(unknown_cinemas)]
        return Programme(cinemas=list(cinemas.values()), screenings=screenings, warnings=warnings)

    def _credits(self, fetcher: Fetcher, cache: Cache, slug: str, warnings: list[str]) -> dict:
        if (cached := cache.get(FILM_CACHE, slug, FILM_CACHE_AGE)) is not None:
            return cached
        try:
            credits = parse_film_page(next_data(fetcher.get(f"{BASE_URL}/filme/{slug}")))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            warnings.append(f"film {slug}: {exc!r}")
            return {}
        if credits["year"] is not None:  # incomplete credits are fetched again next run
            cache.set(FILM_CACHE, slug, credits)
        return credits
