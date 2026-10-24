from datetime import date, datetime
from pathlib import Path

import pytest

from reflick.adapters.lichtblick import (
    BERLIN,
    infer_date,
    parse_credits,
    parse_film_page,
    parse_programme,
)

FIXTURES = Path(__file__).parent / "fixtures" / "lichtblick"
TODAY = date(2026, 10, 24)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_programme_lists_film_pages():
    urls = parse_programme(fixture("programm.html"))
    assert "https://lichtblick-kino.org/casablanca/" in urls
    assert len(urls) == len(set(urls))


def test_film_page_with_midnight_screening():
    url = "https://lichtblick-kino.org/casablanca/"
    [s] = parse_film_page(fixture("casablanca.html"), url, TODAY)
    assert s.title == "Casablanca"
    assert s.language == "OV"
    # Listed as "Sa 24.10. 24:00", which is the start of Sunday.
    assert s.start == datetime(2026, 10, 25, 0, 0, tzinfo=BERLIN)
    assert (s.country, s.year, s.runtime_min) == ("USA", 1942, 102)
    assert s.director == "Michael Curtiz"
    assert "Filmklassiker im Lichtblick-Kino" in s.tags
    assert s.ticket_url.endswith("/show/3664499323")
    assert s.source_url == url


def test_film_page_with_combined_director_credit():
    url = "https://lichtblick-kino.org/invisible-people/"
    [s] = parse_film_page(fixture("invisible-people.html"), url, TODAY)
    assert s.title == "Invisible People"
    assert (s.country, s.year) == ("Frankreich/D", 2025)
    assert s.director == "Alisa Berger"


def test_film_in_series_uses_film_title_not_series_title():
    url = "https://lichtblick-kino.org/reihe/26-10-24-schlingensief-geburtstags-special/united-trash"
    [s] = parse_film_page(fixture("united-trash.html"), url, TODAY)
    assert s.title == "United Trash"
    assert s.series == "Christoph Schlingensief Geburtstags-Special"
    assert s.director == "Christoph Schlingensief"  # "Regie und Kamera: ...; mit: ..."


def test_restoration_label_is_kept_as_tag():
    url = "https://lichtblick-kino.org/trainspotting/"
    [s] = parse_film_page(fixture("trainspotting.html"), url, TODAY)
    assert s.language == "engl. OV"
    assert "Wiederaufführung in 4K" in s.tags
    assert s.director == "Danny Boyle"  # English "Director: ..., Cast: ..."


def test_page_without_film_block_yields_nothing():
    assert parse_film_page("<html><body></body></html>", "x", TODAY) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("24.10.", date(2026, 10, 24)),
        ("04.11.", date(2026, 11, 4)),
        ("10.01.", date(2027, 1, 10)),  # programme reaching into next year
        ("01.10.", date(2026, 10, 1)),  # recent past stays in this year
    ],
)
def test_infer_date(text, expected):
    assert infer_date(text, TODAY) == expected


def test_parse_credits_with_leading_genre():
    facts = parse_credits("Dokumentarfilm, D 2020, 125 min, Regie: Bettina Böhler, mit X")
    assert (facts["country"], facts["year"]) == ("D", 2020)
    assert facts["director"] == "Bettina Böhler"


def test_parse_credits_without_director():
    assert parse_credits("Deutschland 2019, 90 min") == {
        "country": "Deutschland",
        "year": 2019,
        "runtime_min": 90,
    }
