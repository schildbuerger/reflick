"""Zeughauskino in the Deutsches Historisches Museum, Unter den Linden 2, Mitte.

A TYPO3 site whose /zeughauskino/spielplan/ is a Solr search listing, ten
screenings a page (?tx_solr[page]=2), sorted by start time. Each entry has
the start as `datetime="2026-10-24 16:00"`, the title, the series and a few
facts: "Land und Jahr: BRD 1984", "Format: 35mm" and sometimes
"Sprachfassung: OmU". That's usually enough. Screenings with a guest or an
introduction leave the facts out of the listing; only for those is the
screening's own page read ("BRD 1976", "35mm", "R: Werner Herzog, ..., 94'"),
and cached. After the real programme the listing runs on into placeholder
entries dated decades ahead, which the date limit cuts off.
"""

import re
from datetime import datetime, time, timedelta
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

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

BASE_URL = "https://www.dhm.de"
SPIELPLAN_URL = f"{BASE_URL}/zeughauskino/spielplan/?tx_solr%5Bpage%5D={{}}"
DAYS_AHEAD = 180
PAGE_CACHE = "zeughauskino-screening"
PAGE_CACHE_AGE = timedelta(days=30)

CINEMA = Cinema(
    id="zeughauskino",
    name="Zeughauskino",
    address="Unter den Linden 2, 10117 Berlin",
    neighbourhood="Mitte",
    website=f"{BASE_URL}/zeughauskino/",
    lat=52.5177,
    lon=13.397,  # from OpenStreetMap
)


def _facts(item: Tag) -> dict[str, str]:
    """The entry's 'Label: value' lines, e.g. {'Land und Jahr': 'BRD 1984'}."""
    facts = {}
    for label in item.select("li > b"):
        value = label.next_sibling
        facts[clean(label.get_text()).rstrip(":")] = clean(value if isinstance(value, str) else "")
    return facts


COUNTRY_YEAR_RE = re.compile(r"(?:(.+?)\s+)?((?:18|19|20)\d{2})(?:/\d{4})?(?:\s+(.+))?")


def parse_country_year(text: str) -> dict:
    """'BRD 1984', 'BRD/PH 1979/1980' (the first year counts) or '1970 BRD'."""
    m = COUNTRY_YEAR_RE.fullmatch(clean(text))
    if m is None:
        return {}
    return {"country": m.group(1) or m.group(3), "year": int(m.group(2))}


def parse_screening_page(html: str) -> dict:
    """Facts of the (first) film from a screening's own page."""
    soup = BeautifulSoup(html, "html.parser")
    facts: dict = {}
    for node in soup.select(".event-detail__info-text"):
        text = clean(node.get_text(" "))
        if "year" not in facts and len(text) < 40 and (found := parse_country_year(text)):
            facts.update(found)
        elif "director" not in facts and (m := re.match(r"R(?:/B)?:\s*([^,]+)", text)):
            facts["director"] = m.group(1)
            if runtime := re.search(r"(\d+)'", text):
                facts["runtime_min"] = int(runtime.group(1))
        elif "language" not in facts and re.fullmatch(r"Om\w*U|OV|OF|DF|ohne Dialog", text):
            facts["language"] = language_code(text)
    return facts


def parse_item(item: Tag) -> RawScreening | None:
    start = item.select_one("time.events-list-teaser__event-time[datetime]")
    link = item.select_one("h2 a[href]")
    if start is None or link is None:
        return None
    series = item.select_one(".movie-list__tag")
    facts = _facts(item)
    film_format = facts.get("Format")
    return RawScreening(
        cinema_id=CINEMA.id,
        title=clean(link.get_text()),
        start=datetime.fromisoformat(start["datetime"]).replace(tzinfo=BERLIN),
        source_url=urljoin(BASE_URL, link["href"]),
        language=language_code(facts.get("Sprachfassung")),
        series=clean(series.get_text()) or None if series else None,
        tags=[film_format] if film_format else [],
        **parse_country_year(facts.get("Land und Jahr", "")),
    )


def parse_page(html: str) -> tuple[list[RawScreening], bool]:
    """One page of the Spielplan: its screenings, and whether it's the last page."""
    soup = BeautifulSoup(html, "html.parser")
    items = (parse_item(li) for li in soup.select(".events-list-teaser__event-list-item"))
    last = soup.select_one(".search-list__display-more") is None
    return [s for s in items if s], last


class ZeughauskinoAdapter(Adapter):
    id = "zeughauskino"

    def fetch(self, fetcher: Fetcher, cache: Cache | None = None) -> Programme:
        cache = cache or Cache()
        warnings: list[str] = []
        until = datetime.combine(berlin_today() + timedelta(days=DAYS_AHEAD), time(), tzinfo=BERLIN)
        screenings = fetch_pages(fetcher, SPIELPLAN_URL.format, parse_page, until)
        for s in screenings:
            if s.year is not None:
                continue
            for key, value in self._details(fetcher, cache, s.source_url, warnings).items():
                if getattr(s, key) is None:
                    setattr(s, key, value)
        return Programme(cinemas=[CINEMA], screenings=screenings, warnings=warnings)

    def _details(self, fetcher: Fetcher, cache: Cache, url: str, warnings: list[str]) -> dict:
        if (cached := cache.get(PAGE_CACHE, url, PAGE_CACHE_AGE)) is not None:
            return cached
        try:
            facts = parse_screening_page(fetcher.get(url))
        except httpx.HTTPError as exc:
            warnings.append(f"screening {url}: {exc!r}")
            return {}
        # Cached even when empty: talks and symposia never get credits.
        cache.set(PAGE_CACHE, url, facts)
        return facts
