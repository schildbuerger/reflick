"""Kino Krokodil, Greifenhagener Str. 32, Prenzlauer Berg: films from Central
and Eastern Europe.

A WordPress site: /programm/ links every film's page, and a film page lists
all its dates (with a kinoheld ticket link each) and the credits as the first
paragraphs of its text:

    Deutschland 2026, 122 min, deutsche Originalfassung
    Regie: Volker Schlöndorff

Programmes of several films have a line per film instead:

    DER STOFF ZUM LEBEN, 1989, 35mm, 23 min, R: Thomas Kuschel

The dates' <time> elements claim UTC (+00:00) for what are Berlin times, so
the offset is dropped. A typography plugin puts soft hyphens into the text.
"""

import re
from datetime import datetime

from bs4 import BeautifulSoup

from reflick.adapters.base import BERLIN, Adapter, Cache, Fetcher, Programme, clean, language_code
from reflick.models import Cinema, RawScreening

BASE_URL = "https://kino-krokodil.de"
PROGRAMME_URL = f"{BASE_URL}/programm/"

CINEMA = Cinema(
    id="krokodil",
    name="Kino Krokodil",
    address="Greifenhagener Str. 32, 10437 Berlin",
    neighbourhood="Prenzlauer Berg",
    website=f"{BASE_URL}/",
    lat=52.5523,
    lon=13.4194,  # from OpenStreetMap
)

# "Deutschland 2026, 122 min, deutsche Originalfassung"; the language is optional.
CREDITS_RE = re.compile(
    r"(?P<country>[^,]+?)\s+(?P<year>(?:18|19|20)\d{2})(?:\s*/\s*\d{2,4})?,\s*(?P<runtime>\d+)\s*min\.?"
    r"(?:,\s*(?P<language>.+))?"
)
# A film of a programme: "DER STOFF ZUM LEBEN, 1989, 35mm, 23 min, R: Thomas Kuschel".
PROGRAMME_FILM_RE = re.compile(r",\s*(?P<year>(?:18|19|20)\d{2}),.*\bR:\s*(?P<director>.+)")
DIRECTOR_RE = re.compile(r"(?:Regie|R):\s*(.+)")


def _text(node) -> str:
    return clean(node.get_text(" ").replace("\xad", ""))


def parse_programme(html: str) -> list[str]:
    """Film page URLs, in programme order."""
    soup = BeautifulSoup(html, "html.parser")
    links = (a["href"] for a in soup.find_all("a", href=True))
    return list(dict.fromkeys(url for url in links if url.startswith(f"{BASE_URL}/film/")))


def parse_credits(paragraphs: list[str]) -> dict:
    facts: dict = {}
    for line in paragraphs:
        if "year" not in facts and (m := CREDITS_RE.fullmatch(line)):
            facts.update(country=m["country"], year=int(m["year"]), runtime_min=int(m["runtime"]))
            if m["language"]:
                facts["language"] = m["language"]
        elif "director" not in facts and (m := DIRECTOR_RE.match(line)):
            facts["director"] = m.group(1)
    if "year" not in facts:  # a programme: the first film's year and director
        if m := next(filter(None, (PROGRAMME_FILM_RE.search(line) for line in paragraphs)), None):
            facts.setdefault("director", m["director"])
            facts["year"] = int(m["year"])
    return facts


def parse_film_page(html: str, url: str) -> list[RawScreening]:
    soup = BeautifulSoup(html, "html.parser")
    title = _text(soup.find("h1"))
    paragraphs = [_text(p) for p in soup.select(".entry-content p")]
    facts = parse_credits(paragraphs)
    screenings = []
    for time_tag in soup.select(".film__termine time[datetime]"):
        start = datetime.fromisoformat(time_tag["datetime"]).replace(tzinfo=BERLIN)
        link = time_tag.find_parent("a", href=True)
        screenings.append(RawScreening(
            cinema_id=CINEMA.id,
            title=title,
            start=start,
            source_url=url,
            ticket_url=link["href"] if link else None,
            language=language_code(facts.get("language")),
            year=facts.get("year"),
            country=facts.get("country"),
            director=facts.get("director"),
            runtime_min=facts.get("runtime_min"),
        ))
    return screenings


class KrokodilAdapter(Adapter):
    id = "krokodil"

    def fetch(self, fetcher: Fetcher, cache: Cache | None = None) -> Programme:
        screenings: list[RawScreening] = []
        for url in parse_programme(fetcher.get(PROGRAMME_URL)):
            screenings.extend(parse_film_page(fetcher.get(url), url))
        return Programme(cinemas=[CINEMA], screenings=screenings)
