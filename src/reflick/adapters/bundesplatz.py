"""Bundesplatz-Kino, Bundesplatz 14, Wilmersdorf.

A hand-made PHP site. spielplan.php lists the programme by day ("Sonntag,
den 25.10.2026"), each row a time (linked to the cinema's own reservation
page once booking opens) and the film's page (film.php?mid=4991). A
language version is part of the title, "Das geträumte Abenteuer (DF)", and
for older films often the year, "Lola Montès (1955)".

The film pages hold the credits, a series line and a description:

    BRD/Frankreich 1955 | 133 Min.
    Regie: Max Ophüls

The programme has no credits, so every film's page is read, and what it
says (credits and series) kept in the page cache for a month: films run here
for a few weeks.
"""

import re
from datetime import datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from reflick.adapters.base import BERLIN, Adapter, Cache, Fetcher, Programme, clean, language_code
from reflick.models import Cinema, RawScreening

BASE_URL = "https://bundesplatz-kino.de/"
SPIELPLAN_URL = urljoin(BASE_URL, "spielplan.php")
PAGE_CACHE = "bundesplatz-film"
PAGE_CACHE_AGE = timedelta(days=30)

CINEMA = Cinema(
    id="bundesplatz",
    name="Bundesplatz-Kino",
    address="Bundesplatz 14, 10715 Berlin",
    neighbourhood="Wilmersdorf",
    website=BASE_URL,
    lat=52.4789,
    lon=13.3294,  # from OpenStreetMap
)

DAY_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
LANGUAGE_SUFFIX_RE = re.compile(r"\s*\((DF|OV|OF|OmU|OmeU|OmdU|OmdeU)!?\)$")
CREDITS_RE = re.compile(r"(.+?)\s+((?:18|19|20)\d{2})(?:/\d{2,4})?\s*\|\s*(\d+)\s*Min")
DIRECTOR_RE = re.compile(r"Regie(?:\s+und\s+Drehbuch)?\s*:\s*(.+)")
TITLE_YEAR_RE = re.compile(r"\(((?:18|19|20)\d{2})\)$")


def split_language(title: str) -> tuple[str, str | None]:
    """'Das geträumte Abenteuer (DF)' -> ('Das geträumte Abenteuer', 'DF')."""
    if m := LANGUAGE_SUFFIX_RE.search(title):
        return title[: m.start()], m.group(1)
    return title, None


def parse_spielplan(html: str) -> list[RawScreening]:
    """Rows belong to the day heading above them. (The page's unclosed tags
    nest the days' sections inside each other, so sections can't tell.)"""
    soup = BeautifulSoup(html, "html.parser")
    screenings = []
    for row in soup.find_all("div", style=re.compile(r"display:\s*flex")):
        heading = row.find_previous("h3")
        day = DAY_RE.search(heading.get_text()) if heading else None
        cells = row.find_all("div", recursive=False)
        film = row.find("a", href=re.compile(r"film\.php\?mid="))
        if not day or len(cells) < 2 or film is None:
            continue
        d, m, y = (int(x) for x in day.groups())
        hour, minute = (int(x) for x in clean(cells[0].get_text()).split(":"))
        reservation = cells[0].find("a", href=True)
        title, language = split_language(clean(film.get_text(" ")))
        year = TITLE_YEAR_RE.search(title)
        screenings.append(RawScreening(
            cinema_id=CINEMA.id,
            title=title,
            start=datetime(y, m, d, hour, minute, tzinfo=BERLIN),
            source_url=urljoin(BASE_URL, film["href"]),
            ticket_url=urljoin(BASE_URL, reservation["href"]) if reservation else None,
            language=language_code(language),
            year=int(year.group(1)) if year else None,  # until the film page says
        ))
    return screenings


def parse_film_page(html: str) -> dict:
    """Credits and series from a film page; whatever of them it has."""
    soup = BeautifulSoup(html, "html.parser")
    facts: dict = {}
    # The italic line under the title: a series, or sometimes "Ein Film von ...".
    series = soup.find("span", style=re.compile(r"font-style:\s*italic"))
    if series and not clean(series.get_text(" ")).startswith("Ein Film von"):
        facts["series"] = clean(series.get_text(" "))
    for br in soup.find_all("br"):  # lines end at <br>, not at every tag
        br.replace_with("\n")
    for line in (clean(x) for p in soup.find_all("p") for x in p.get_text().split("\n")):
        if "year" not in facts and (m := CREDITS_RE.match(line)):
            facts["country"], facts["year"], facts["runtime_min"] = m.group(1), int(m.group(2)), int(m.group(3))
        elif "director" not in facts and (m := DIRECTOR_RE.match(line)):
            facts["director"] = m.group(1)
    return facts


class BundesplatzAdapter(Adapter):
    id = "bundesplatz"

    def fetch(self, fetcher: Fetcher, cache: Cache | None = None) -> Programme:
        cache = cache or Cache()
        warnings: list[str] = []
        screenings = parse_spielplan(fetcher.get(SPIELPLAN_URL))
        pages: dict[str, dict] = {}
        for s in screenings:
            if s.source_url not in pages:
                pages[s.source_url] = self._film(fetcher, cache, s.source_url, warnings)
            facts = pages[s.source_url]
            s.series = facts.get("series")
            s.year, s.country = facts.get("year") or s.year, facts.get("country")
            s.director, s.runtime_min = facts.get("director"), facts.get("runtime_min")
        return Programme(cinemas=[CINEMA], screenings=screenings, warnings=warnings)

    def _film(self, fetcher: Fetcher, cache: Cache, url: str, warnings: list[str]) -> dict:
        if (known := cache.get(PAGE_CACHE, url, PAGE_CACHE_AGE)) is not None:
            return known
        try:
            facts = parse_film_page(fetcher.get(url))
        except Exception as exc:  # a broken film page mustn't lose the screening
            warnings.append(f"film page {url}: {exc!r}")
            return {}
        cache.set(PAGE_CACHE, url, facts)
        return facts
