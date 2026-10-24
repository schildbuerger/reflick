from datetime import date, datetime
from pathlib import Path

import httpx
import pytest

from reflick.adapters.zeughauskino import (
    BASE_URL,
    BERLIN,
    SPIELPLAN_URL,
    ZeughauskinoAdapter,
    parse_country_year,
    parse_page,
    parse_screening_page,
)
from reflick.revival import is_revival

FIXTURES = Path(__file__).parent / "fixtures" / "zeughauskino"
TODAY = date(2026, 10, 24)

HERZ_AUS_GLAS = f"{BASE_URL}/zeughauskino/vorfuehrung/default-title-14849/"
ICH_LIEBE_DICH = f"{BASE_URL}/zeughauskino/vorfuehrung/default-title-14871/"
SUKKUBUS = f"{BASE_URL}/zeughauskino/vorfuehrung/default-title-14907/"

PAGES = {
    SPIELPLAN_URL.format(1): "spielplan-1.html",
    SPIELPLAN_URL.format(2): "spielplan-2.html",
    HERZ_AUS_GLAS: "vorfuehrung-14849.html",
    ICH_LIEBE_DICH: "vorfuehrung-14871.html",
}


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeFetcher:
    def __init__(self):
        self.requested: list[str] = []

    def get(self, url: str) -> str:
        self.requested.append(url)
        if url not in PAGES:
            request = httpx.Request("GET", url)
            raise httpx.HTTPStatusError("404", request=request, response=httpx.Response(404, request=request))
        return fixture(PAGES[url])


class MemoryCache:
    def __init__(self):
        self.data = {}

    def get(self, namespace, key, max_age):
        return self.data.get((namespace, key))

    def set(self, namespace, key, value):
        self.data[(namespace, key)] = value


def test_listing_entry_with_facts():
    screenings, last = parse_page(fixture("spielplan-1.html"))
    assert not last
    s = screenings[0]
    assert s.title == "Der Prozeß"
    assert s.start == datetime(2026, 10, 24, 16, 0, tzinfo=BERLIN)
    assert (s.country, s.year) == ("BRD", 1984)
    assert s.tags == ["Digital SD"]
    assert s.series == "Lebensläufe"
    assert is_revival(s, TODAY)


def test_listing_entry_with_language():
    screenings, _ = parse_page(fixture("spielplan-1.html"))
    [s] = [s for s in screenings if s.title.startswith("Lagaan")]
    assert (s.language, s.year) == ("OmeU", 2001)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("BRD 1984", {"country": "BRD", "year": 1984}),
        ("BRD/PH 1979/1980", {"country": "BRD/PH", "year": 1979}),
        ("1970 BRD", {"country": "BRD", "year": 1970}),
        ("Einführung: Tilman Schumacher", {}),
    ],
)
def test_parse_country_year(text, expected):
    assert parse_country_year(text) == expected


def test_screening_page_with_introduction():
    facts = parse_screening_page(fixture("vorfuehrung-14849.html"))
    assert facts == {"country": "BRD", "year": 1976, "director": "Werner Herzog"}


def test_screening_page_with_year_first_and_runtime():
    facts = parse_screening_page(fixture("vorfuehrung-14871.html"))
    assert facts == {"country": "BRD", "year": 1970, "director": "Uwe Brandner", "runtime_min": 95}


def test_adapter_stops_at_placeholder_dates_and_fills_missing_facts():
    cache = MemoryCache()
    fetcher = FakeFetcher()
    programme = ZeughauskinoAdapter().fetch(fetcher, cache)
    titles = [s.title for s in programme.screenings]
    assert "Berlin um die Ecke" not in titles  # listed for 2064
    assert len(programme.screenings) == 5
    [herz] = [s for s in programme.screenings if s.title == "Herz aus Glas"]
    assert (herz.year, herz.director) == (1976, "Werner Herzog")
    # Sukkubus has no page in the fixtures: reported, not cached, the rest still works.
    assert programme.warnings == [f"screening {SUKKUBUS}: HTTPStatusError('404')"]
    assert ("zeughauskino-screening", SUKKUBUS) not in cache.data

    again = FakeFetcher()
    ZeughauskinoAdapter().fetch(again, cache)
    assert HERZ_AUS_GLAS not in again.requested  # cached
