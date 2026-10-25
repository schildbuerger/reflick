from datetime import date, datetime
from pathlib import Path

import httpx

from reflick.adapters import transtopia
from reflick.adapters.transtopia import BERLIN, CALENDAR_URL, TranstopiaAdapter, parse_calendar, parse_film_page
from reflick.languages import language_version
from reflick.revival import is_revival

FIXTURES = Path(__file__).parent / "fixtures" / "transtopia"
TODAY = date(2026, 10, 25)
MAS_ALLA = "https://sinematranstopia.com/de/film-restored-risky-business/mas-alla-del-olvido"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def by_title(screenings, title):
    [s] = [s for s in screenings if s.title == title]
    return s


def test_calendar_entry_with_series_and_credits():
    s = by_title(parse_calendar(fixture("calendar.html")), "Más allá del olvido")
    # Printed as 11:00; the page's <time> wrongly says 11:00 UTC.
    assert s.start == datetime(2026, 10, 25, 11, 0, tzinfo=BERLIN)
    assert s.series == "Film Restored - Risky Business"
    assert s.original_title == "Beyond Oblivion"
    assert (s.director, s.country, s.year) == ("Hugo del Carril", "Argentinien", 1956)
    assert s.source_url == MAS_ALLA
    assert s.ticket_url.startswith("https://booking.cinetixx.de/")
    assert is_revival(s, TODAY)


def test_programme_without_credits_and_cafe_talks():
    screenings = parse_calendar(fixture("calendar.html"))
    s = by_title(screenings, "Queer Fantasies")  # a short-film programme
    assert (s.director, s.country, s.year, s.original_title) == (None, None, None, None)
    # The HANE Salon talk on the same evening is left out.
    assert [s.title for s in screenings if s.start.date() == date(2026, 10, 31)] == ["ADIRA"]
    assert len(screenings) == 7


def test_film_page_runtime_and_language():
    facts = parse_film_page(fixture("mas-alla-del-olvido.html"))
    assert facts == {"runtime_min": 94, "language": "Spanisch mit englischen Untertitel"}
    assert language_version(facts["language"]) == "OmeU"


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
        self.films = {}

    def film(self, source, key):
        return self.films.get((source, key))

    def save_film(self, source, key, credits):
        self.films[(source, key)] = credits


def test_adapter_reads_film_pages_of_revival_candidates_only(monkeypatch):
    monkeypatch.setattr(transtopia, "berlin_today", lambda: TODAY)
    fetcher = FakeFetcher({CALENDAR_URL: "calendar.html", MAS_ALLA: "mas-alla-del-olvido.html"})
    cache = MemoryCache()
    programme = TranstopiaAdapter().fetch(fetcher, cache)

    s = by_title(programme.screenings, "Más allá del olvido")
    assert (s.runtime_min, s.language) == (94, "Spanisch mit englischen Untertitel")
    assert cache.films[("transtopia", MAS_ALLA)]["runtime_min"] == 94
    # Pages of the other old films are missing from the fake site: warned
    # about, but their screenings stay. Recent films' pages aren't read.
    assert all("2025" not in url for url in fetcher.requested)
    assert len(programme.warnings) == 3  # Kuu on vaarallinen, Drakula, Wie das Meer
    assert by_title(programme.screenings, "Kuu on vaarallinen").language is None

    # The next run takes the stored facts: no page requests for that film.
    again = FakeFetcher({CALENDAR_URL: "calendar.html"})
    TranstopiaAdapter().fetch(again, cache)
    assert MAS_ALLA not in again.requested
