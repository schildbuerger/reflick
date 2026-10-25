from datetime import date, datetime
from pathlib import Path

import pytest

from reflick.adapters import filmkunst66
from reflick.adapters.filmkunst66 import (
    BERLIN,
    PROGRAMME_URL,
    Filmkunst66Adapter,
    parse_flyer,
    split_title,
    week_start,
)
from reflick.revival import is_revival

FIXTURES = Path(__file__).parent / "fixtures" / "filmkunst66"
TODAY = date(2026, 10, 25)
FLYER_URL = "https://filmkunst66.de/fileadmin/user_upload/Wochenflyer_Filmkunst66_22.-28.10.2026.pdf"


def flyer_text() -> str:
    return (FIXTURES / "wochenflyer-22-28-10-2026.txt").read_text(encoding="utf-8")


def times(title):
    return [s.start for s in parse_flyer(flyer_text()) if s.title == title]


def test_times_belong_to_the_weekday_columns():
    # "Adams Acht 14:45" Thursday to Tuesday, nothing on Wednesday.
    assert times("Adams Acht") == [datetime(2026, 10, d, 14, 45, tzinfo=BERLIN) for d in range(22, 28)]
    # The second screen's table, whose columns sit slightly differently.
    assert times("KiFiMo: D. kleine Hexe") == [datetime(2026, 10, 23, 14, 30, tzinfo=BERLIN)]


def test_title_over_two_lines_with_two_rows_of_times():
    heimsuchung = times("Heimsuchung – Eine Jahrhundertgeschichte")
    assert len(heimsuchung) == 13  # 17:15 and 20:00 most days, not 20:00 on Monday
    assert datetime(2026, 10, 26, 20, 0, tzinfo=BERLIN) not in heimsuchung
    assert times("Frau Winkler verlässt das Haus")[0] == datetime(2026, 10, 22, 15, 30, tzinfo=BERLIN)


def test_a_row_of_times_without_title_belongs_to_the_film_above():
    sinn = times("Sinn und Sinnlichkeit (2026)")
    assert datetime(2026, 10, 24, 15, 15, tzinfo=BERLIN) in sinn  # first row
    assert datetime(2026, 10, 25, 17, 45, tzinfo=BERLIN) in sinn  # second row
    assert len(sinn) == 9


def test_language_versions_and_years():
    [s] = [s for s in parse_flyer(flyer_text()) if s.title == "Sense and Sensibility"]
    assert (s.year, s.language, s.start) == (2026, "OmU", datetime(2026, 10, 26, 20, 30, tzinfo=BERLIN))
    [s] = [s for s in parse_flyer(flyer_text()) if s.title == "Heimsuchung"]
    assert s.language == "OmeU"
    [hunde] = [s for s in parse_flyer(flyer_text()) if s.title == "Ein Haufen toller Hunde (1965)"]
    assert hunde.year == 1965 and is_revival(hunde, TODAY)
    assert len(parse_flyer(flyer_text())) == 50


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Sense and Sensibility (2026, OmU)", ("Sense and Sensibility", 2026, "OmU")),
        ("Heimsuchung (OmeU!)", ("Heimsuchung", None, "OmeU")),
        ("Lola Montès (1955)", ("Lola Montès (1955)", 1955, None)),
        ("Pulse (Kairo)", ("Pulse (Kairo)", None, None)),
        ("Adams Acht", ("Adams Acht", None, None)),
    ],
)
def test_split_title(title, expected):
    assert split_title(title) == expected


def test_week_start_across_new_year():
    assert week_start("Filmprogramm   Donnerstag, 22.10. – Mittwoch, 28.10.26") == date(2026, 10, 22)
    assert week_start("Donnerstag, 31.12. – Mittwoch, 06.01.27") == date(2026, 12, 31)
    with pytest.raises(ValueError):
        week_start("Programm folgt")


class FakeFetcher:
    def __init__(self, page: str):
        self.page = page
        self.requested: list[str] = []

    def get(self, url: str) -> str:
        self.requested.append(url)
        return self.page

    def get_bytes(self, url: str) -> bytes:
        self.requested.append(url)
        return b"%PDF"


def test_adapter_reads_the_linked_flyer(monkeypatch):
    monkeypatch.setattr(filmkunst66, "pdf_text", lambda data: flyer_text())
    page = (
        '<a href="/fileadmin/user_upload/Wochenflyer_Filmkunst66_22.-28.10.2026.pdf">Wochenflyer</a>'
        '<a href="/fileadmin/user_upload/indiekino_magazin_2026-10.pdf">Indiekino</a>'
    )
    fetcher = FakeFetcher(page)
    programme = Filmkunst66Adapter().fetch(fetcher)
    assert fetcher.requested == [PROGRAMME_URL, FLYER_URL]
    assert len(programme.screenings) == 50
    assert programme.warnings == []


def test_adapter_warns_without_a_flyer():
    programme = Filmkunst66Adapter().fetch(FakeFetcher("<p>Programm folgt</p>"))
    assert programme.screenings == []
    assert programme.warnings == ["no weekly flyer linked on the programme page"]
