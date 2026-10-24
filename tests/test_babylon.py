from datetime import datetime
from pathlib import Path

import pytest

from reflick.adapters.babylon import (
    BERLIN,
    BabylonAdapter,
    clean_title,
    parse_credits,
    parse_film_page,
    parse_programme,
    split_series,
)

FIXTURES = Path(__file__).parent / "fixtures" / "babylon"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def by_title(screenings, title):
    [s] = [s for s in screenings if s.title == title]
    return s


@pytest.fixture
def programme():
    return parse_programme(fixture("programm.html"))


def test_series_entry(programme):
    s = by_title(programme, "Dr. Strangelove or: How I Learned to Stop Worrying and Love the Bomb")
    assert s.series == "Clockwork Kubrick"
    assert s.start == datetime(2026, 10, 24, 20, 0, tzinfo=BERLIN)
    assert s.runtime_min == 95
    assert s.source_url.startswith("https://babylonberlin.eu/programm/festivals/clockwork-kubrick/")
    assert s.year is None  # the programme's credit line is cut off before the year


def test_series_prefix_recognised_under_plain_film_category(programme):
    s = by_title(programme, "The Shining")
    assert s.series == "Clockwork Kubrick"
    assert (s.country, s.year, s.director, s.language) == ("USA", 1980, "Stanley Kubrick", "OmU")


def test_language_bracket_removed_from_title(programme):
    s = by_title(programme, "Fitzcarraldo")
    assert s.series == "Kinski 100!"
    assert (s.year, s.director, s.language) == (1982, "Werner Herzog", "OmU")


def test_english_credit_line(programme):
    s = by_title(programme, "The Exorcist: Director's Cut")
    assert s.series is None
    assert (s.year, s.director) == (1973, "William Friedkin")


def test_silent_film_with_orchestra(programme):
    s = next(s for s in programme if s.title.startswith("Metropolis"))
    assert (s.country, s.year, s.language) == ("D", 1927, "OmeU")
    assert "stummfilm-live" in s.tags


def test_stage_shows_are_skipped(programme):
    assert not any("Gattano" in s.title for s in programme)


def test_new_film_keeps_its_own_colon_title(programme):
    s = by_title(programme, "Jailer 2")
    assert s.series == "IndoGerman Film"  # matched via its "indogerman" tag
    assert s.year == 2026


def test_film_page_fills_in_missing_year():
    assert parse_film_page(fixture("dr-strangelove.html")) == {
        "country": "USA",
        "year": 1964,
        "director": "Stanley Kubrick",
        "language": "OmU",
    }


class FakeFetcher:
    def __init__(self, pages: dict[str, str]):
        self.pages = pages
        self.requested: list[str] = []

    def get(self, url: str) -> str:
        self.requested.append(url)
        return self.pages.get(url, "<html><body></body></html>")


def test_adapter_reads_film_page_only_when_year_is_missing():
    strangelove = next(
        s.source_url for s in parse_programme(fixture("programm.html")) if "Strangelove" in s.title
    )
    fetcher = FakeFetcher({
        "https://babylonberlin.eu/programm": fixture("programm.html"),
        strangelove: fixture("dr-strangelove.html"),
    })
    screenings = BabylonAdapter().fetch(fetcher)
    s = next(s for s in screenings if "Strangelove" in s.title)
    assert (s.year, s.language) == (1964, "OmU")
    # Exorcist, Shining etc. already have a year: no extra requests for them.
    assert strangelove in fetcher.requested
    assert not any("exorcist" in url for url in fetcher.requested)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[OV] USA, 1955, R: Stanley Kubrick mit Jamie…", ("USA", 1955, "Stanley Kubrick")),
        ("ITA/D/Schw 2013, R: Alice Rohrwacher mit Maria…", ("ITA/D/Schw", 2013, "Alice Rohrwacher")),
        ("- OmeU (German, ENGLISH with Engl. Subt.) BRD 1972, R:…", ("BRD", 1972, None)),
    ],
)
def test_parse_credits(text, expected):
    facts = parse_credits(text)
    assert (facts.get("country"), facts.get("year"), facts.get("director")) == expected


def test_split_series_needs_a_matching_name():
    assert split_series("Kinski 100!: Aguirre, der Zorn Gottes", ["KINSKI 100!"]) == (
        "Aguirre, der Zorn Gottes",
        "Kinski 100!",
    )
    assert split_series("2001: A Space Odyssey", ["KINSKI 100!"]) == ("2001: A Space Odyssey", None)


def test_clean_title():
    assert clean_title("Metropolis  (OmeU) LIVE Babylon Orchester Berlin") == (
        "Metropolis LIVE Babylon Orchester Berlin"
    )
    assert clean_title("Clockwork Kubrick: Killer`s Kiss") == "Clockwork Kubrick: Killer's Kiss"
