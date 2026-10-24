from datetime import date, datetime
from pathlib import Path

import pytest

from reflick.adapters.hoefe import (
    BASE_URL,
    BERLIN,
    PROGRAMME_URL,
    HoefeAdapter,
    infer_date,
    parse_facts,
    parse_film_page,
    parse_programme,
)
from reflick.revival import is_revival

FIXTURES = Path(__file__).parent / "fixtures" / "hoefe"
TODAY = date(2026, 10, 24)

COBRA_VERDE = f"{BASE_URL}/filme/cobra-verde-52404/"
EMIL = f"{BASE_URL}/filme/emil-und-die-detektive-52473/"
FRITZ_BAUER = f"{BASE_URL}/filme/staat-gegen-fritz-bauer-der-53167/"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_programme_lists_film_pages_once_each():
    assert parse_programme(fixture("programm.html")) == [EMIL, COBRA_VERDE, FRITZ_BAUER]


def test_35mm_special():
    [s] = parse_film_page(fixture("cobra-verde.html"), COBRA_VERDE, TODAY)
    assert s.title == "Cobra Verde"
    assert s.start == datetime(2026, 10, 30, 22, 0, tzinfo=BERLIN)
    assert s.language == "OmeU"
    assert (s.country, s.year, s.runtime_min) == ("Bundesrepublik Deutschland", 1987, 106)
    assert s.director == "Werner Herzog"
    assert s.series == "35mm-Kinospecial: Klaus Kinski zum 100. Geburtstag"
    assert s.tags == ["35mm"]
    assert s.ticket_url.endswith("showId=914686")
    assert s.source_url == COBRA_VERDE
    assert is_revival(s, TODAY)


def test_german_screenings_have_no_language_and_a_note_is_no_series():
    screenings = parse_film_page(fixture("emil-und-die-detektive.html"), EMIL, TODAY)
    assert [s.start.date() for s in screenings] == [date(2026, 10, d) for d in range(24, 29)]
    assert {s.language for s in screenings} == {None}
    assert screenings[0].series is None  # label is "Altersempfehlung der JFJ: 8 bis 99"
    assert not is_revival(screenings[0], TODAY)


def test_film_without_year_in_series():
    [s] = parse_film_page(fixture("staat-gegen-fritz-bauer.html"), FRITZ_BAUER, TODAY)
    assert s.start == datetime(2027, 1, 13, 19, 0, tzinfo=BERLIN)
    assert (s.year, s.country) == (None, None)
    assert s.director == "Lars Kraume"
    assert s.series == "Was bleibt? Vier Filme über den Nationalsozialismus"


def test_page_without_film_details_yields_nothing():
    assert parse_film_page(fixture("programm.html"), PROGRAMME_URL, TODAY) == []


def test_adapter_reads_every_film_page():
    pages = {
        PROGRAMME_URL: "programm.html",
        COBRA_VERDE: "cobra-verde.html",
        EMIL: "emil-und-die-detektive.html",
        FRITZ_BAUER: "staat-gegen-fritz-bauer.html",
    }

    class FakeFetcher:
        def get(self, url):
            return fixture(pages[url])

    programme = HoefeAdapter().fetch(FakeFetcher())
    assert len(programme.screenings) == 7
    assert programme.warnings == []


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Freitag 30. Oktober", date(2026, 10, 30)),
        ("Mittwoch 13. Januar", date(2027, 1, 13)),
        ("Dienstag 1. September", date(2026, 9, 1)),  # recent past stays this year
        ("Montag 2. März", date(2027, 3, 2)),
    ],
)
def test_infer_date(text, expected):
    assert infer_date(text, TODAY) == expected


@pytest.mark.parametrize(
    "label",
    [
        "Preview am 1. November um 11 Uhr!",
        "Am Sonntag, den 15. November um 13:00 Uhr",
        "Gewinner vom Preis der Jury in Cannes",
        "Sprachfassung beachten!",
    ],
)
def test_notes_are_not_series(label):
    html = fixture("cobra-verde.html").replace(
        "35mm-Kinospecial: Klaus Kinski zum 100. Geburtstag", label
    )
    [s] = parse_film_page(html, COBRA_VERDE, TODAY)
    assert s.series is None
    assert s.tags == []


def test_parse_facts_with_several_countries():
    facts = parse_facts(["AB 0 JAHREN / 81 MINUTEN / deutsch", "Deutschland/ Österreich/ Spanien 2026"])
    assert facts == {"runtime_min": 81, "country": "Deutschland/ Österreich/ Spanien", "year": 2026}
