"""SİNEMA TRANSTOPIA, Lindower Str. 20/22, Wedding (bi'bak's cinema).

The calendar (/de/calendar) lists every screening for about a month on one
page: start time, series, title (the original, often followed by a second
title line, mostly the English one), director, country and year, and a
cinetixx ticket link. Its <time> elements
claim UTC (+00:00) for what are Berlin times, so the printed "25.10.2026
11:00" is read instead.

Language version and runtime are only on the film's own page, in a line like

    Hugo del Carril, Argentinien 1956, 94 Min., Spanisch mit englischen Untertitel

which is read for revival candidates only and kept in the films table.
Events of the café's HANE Salon series are talks, not films, and skipped.
"""

import re
from datetime import date, datetime

from bs4 import BeautifulSoup, Tag

from reflick.adapters.base import (
    BERLIN,
    Adapter,
    Cache,
    Fetcher,
    Programme,
    berlin_today,
    clean,
    language_code,
)
from reflick.models import Cinema, RawScreening
from reflick.revival import MIN_AGE_YEARS

BASE_URL = "https://sinematranstopia.com"
CALENDAR_URL = f"{BASE_URL}/de/calendar"
SKIP_SERIES = ("hane",)  # the café's talks and salons

CINEMA = Cinema(
    id="transtopia",
    name="Sinema Transtopia",
    address="Lindower Str. 20/22, 13347 Berlin",
    neighbourhood="Wedding",
    website=f"{BASE_URL}/de",
    lat=52.5436,
    lon=13.3675,  # from OpenStreetMap
)

YEAR_RE = re.compile(r"(?:18|19|20)\d{2}")


def _texts(block: Tag, css_class: str | None) -> list[str]:
    """Texts of the block's child divs with exactly this class (None: no class)."""
    wanted = css_class.split() if css_class else None
    return [clean(d.get_text(" ")) for d in block.find_all("div", recursive=False) if d.get("class") == wanted]


def parse_entry(entry: Tag) -> RawScreening | None:
    """One calendar entry; None for the café's talks."""
    time_tag = entry.find("time")
    info = entry.find("div", class_="grow")
    link = info.find("a", href=True) if info else None
    if time_tag is None or link is None:
        return None
    start = datetime.strptime(clean(time_tag.get_text()), "%d.%m.%Y %H:%M").replace(tzinfo=BERLIN)
    series = next(iter(_texts(info, "font-sans-bold italic uppercase")), None)
    if series and series.casefold().startswith(SKIP_SERIES):
        return None
    # The first bold line is the title (the link); a second one is another
    # title, mostly the English one.
    title = clean(link.get_text(" "))
    other_title = next((t for t in _texts(info, "font-sans-bold") if t and t != title), None)
    italics = [t for t in _texts(info, "font-sans-italic") if t]
    year = next((int(t) for t in italics if YEAR_RE.fullmatch(t)), None)
    country = next((t for t in italics if not YEAR_RE.fullmatch(t)), None)
    director = next((t for t in _texts(info, None) if t), None)  # short-film programmes have none
    ticket = entry.find("a", href=re.compile(r"cinetixx"))
    return RawScreening(
        cinema_id=CINEMA.id,
        title=title,
        start=start,
        source_url=link["href"],
        ticket_url=ticket["href"] if ticket else None,
        series=series,
        year=year,
        country=country,
        director=director,
        # Mostly the English title, which OMDb and Wikidata often know a film by.
        original_title=other_title,
    )


def parse_calendar(html: str) -> list[RawScreening]:
    soup = BeautifulSoup(html, "html.parser")
    entries = (parse_entry(div) for div in soup.select("div.flex.group") if div.find("time"))
    return [s for s in entries if s]


def parse_film_page(html: str) -> dict:
    """Runtime and language version from the line under the film's title."""
    soup = BeautifulSoup(html, "html.parser")
    blocks = (d for d in soup.select("div.mt-8") if d.find("span", class_="font-sans-bold"))
    line = next((clean(d.get_text(" ")) for d in blocks), "")
    facts: dict = {}
    if runtime := re.search(r"(\d+)\s*Min\.?", line):
        facts["runtime_min"] = int(runtime.group(1))
        # Whatever follows the runtime is the language version.
        if language := clean(line[runtime.end():].strip(" ,.")):
            facts["language"] = language
    return facts


def is_candidate(s: RawScreening, today: date) -> bool:
    """Old enough to be a revival, so worth reading the film's page."""
    return s.year is not None and today.year - s.year >= MIN_AGE_YEARS


class TranstopiaAdapter(Adapter):
    id = "transtopia"

    def fetch(self, fetcher: Fetcher, cache: Cache | None = None) -> Programme:
        cache = cache or Cache()
        today = berlin_today()
        warnings: list[str] = []
        screenings = parse_calendar(fetcher.get(CALENDAR_URL))
        pages: dict[str, dict] = {}
        for s in screenings:
            if not is_candidate(s, today):
                continue
            if s.source_url not in pages:
                pages[s.source_url] = self._film(fetcher, cache, s.source_url, warnings)
            facts = pages[s.source_url]
            s.runtime_min = facts.get("runtime_min")
            s.language = language_code(facts.get("language"))
        return Programme(cinemas=[CINEMA], screenings=screenings, warnings=warnings)

    def _film(self, fetcher: Fetcher, cache: Cache, url: str, warnings: list[str]) -> dict:
        if (known := cache.film(self.id, url)) is not None:
            return known
        try:
            facts = parse_film_page(fetcher.get(url))
        except Exception as exc:  # a broken film page mustn't lose the screening
            warnings.append(f"film page {url}: {exc!r}")
            return {}
        if facts:
            cache.save_film(self.id, url, facts)
        return facts
