from datetime import date, datetime
from pathlib import Path

import httpx

from reflick.adapters.bundesplatz import (
    BERLIN,
    PAGE_CACHE,
    SPIELPLAN_URL,
    BundesplatzAdapter,
    parse_film_page,
    parse_spielplan,
    split_language,
)
from reflick.revival import is_revival

FIXTURES = Path(__file__).parent / "fixtures" / "bundesplatz"
TODAY = date(2026, 10, 25)
LOLA = "https://bundesplatz-kino.de/film.php?mid=4991"
FREYA = "https://bundesplatz-kino.de/film.php?mid=4887"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def by_title(screenings, title):
    return [s for s in screenings if s.title == title]


def test_spielplan_by_day():
    screenings = parse_spielplan(fixture("spielplan.html"))
    # Only the day listings count, not the sidebar's "today" box.
    assert len(screenings) == 16
    [lola] = by_title(screenings, "Lola Montès (1955)")
    assert lola.start == datetime(2026, 10, 25, 15, 30, tzinfo=BERLIN)
    assert lola.source_url == LOLA
    assert lola.year == 1955  # from the title, until the film page says
    # Rows belong to their own day, though the page's sections nest.
    [winkler, *_] = by_title(screenings, "Frau Winkler verlässt das Haus")
    assert winkler.start == datetime(2026, 10, 26, 15, 30, tzinfo=BERLIN)
    assert winkler.ticket_url == "https://bundesplatz-kino.de/reservierung.php?vid=20738"


def test_language_version_in_the_title():
    [s] = by_title(parse_spielplan(fixture("spielplan.html")), "Das geträumte Abenteuer")
    assert s.language == "DF"
    assert split_language("Heimsuchung (OmeU!)") == ("Heimsuchung", "OmeU")
    assert split_language("Lola Montès (1955)") == ("Lola Montès (1955)", None)


def test_film_page_credits_and_series():
    assert parse_film_page(fixture("film-4991.html")) == {
        "series": "HOMMAGE HELMUT RINGELMANN - ZUM 100. GEBURTSTAG",
        "country": "BRD/Frankreich", "year": 1955, "runtime_min": 133, "director": "Max Ophüls",
    }


def test_film_page_with_only_directors():
    # "Ein Film von ..." under the title isn't a series.
    assert parse_film_page(fixture("film-4887.html")) == {"director": "Antje Starost, Hans Helmut Grotjahn"}


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.requested: list[str] = []

    def get(self, url: str) -> str:
        self.requested.append(url)
        if url not in self.pages:
            request = httpx.Request("GET", url)
            raise httpx.HTTPStatusError("404", request=request, response=httpx.Response(404, request=request))
        return fixture(self.pages[url])


class MemoryCache:
    def __init__(self):
        self.data = {}

    def get(self, namespace, key, max_age):
        return self.data.get((namespace, key))

    def set(self, namespace, key, value):
        self.data[(namespace, key)] = value


def test_adapter_fills_in_film_pages_once():
    pages = {SPIELPLAN_URL: "spielplan.html", LOLA: "film-4991.html", FREYA: "film-4887.html"}
    fetcher = FakeFetcher(pages)
    cache = MemoryCache()
    programme = BundesplatzAdapter().fetch(fetcher, cache)

    [lola] = by_title(programme.screenings, "Lola Montès (1955)")
    assert (lola.director, lola.country, lola.runtime_min) == ("Max Ophüls", "BRD/Frankreich", 133)
    assert lola.series == "HOMMAGE HELMUT RINGELMANN - ZUM 100. GEBURTSTAG"
    assert is_revival(lola, TODAY)
    [freya] = by_title(programme.screenings, "Geschichte einer Liebe - Freya (2016)")
    assert (freya.year, freya.director) == (2016, "Antje Starost, Hans Helmut Grotjahn")
    assert fetcher.requested.count(LOLA) == 1  # once per film, not per screening
    assert (PAGE_CACHE, LOLA) in cache.data
    # The other films' pages aren't in the fake site: warned about, kept.
    assert programme.warnings and all("film page" in w for w in programme.warnings)
    assert len(programme.screenings) == 16

    again = FakeFetcher(pages)
    BundesplatzAdapter().fetch(again, cache)
    assert LOLA not in again.requested
