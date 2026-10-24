from datetime import date, datetime
from pathlib import Path

from reflick.adapters.arsenal import BERLIN, CALENDAR_URL, ArsenalAdapter, parse_page, parse_start
from reflick.revival import is_revival

FIXTURES = Path(__file__).parent / "fixtures" / "arsenal"
TODAY = date(2026, 10, 24)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def by_title(screenings, title):
    [s] = [s for s in screenings if s.title == title]
    return s


def test_event_with_full_credits():
    screenings, last = parse_page(fixture("calendar-1.json"), TODAY)
    assert not last
    s = by_title(screenings, "Caravaggio")
    assert s.start == datetime(2026, 10, 24, 17, 0, tzinfo=BERLIN)
    assert (s.director, s.country, s.year, s.runtime_min) == ("Derek Jarman", "UK", 1986, 93)
    assert s.language == "OmdU"
    assert s.series == "MHT – Production Design (2)"
    assert s.tags == ["DCP"]
    assert s.ticket_url == "https://kinotickets.express/arsenal-berlin/booking/9726"
    assert s.source_url == "https://www.arsenal-berlin.de/kino/filmvorfuehrung/caravaggio-5868/"
    assert is_revival(s, TODAY)


def test_foyer_installation_is_skipped():
    screenings, _ = parse_page(fixture("calendar-1.json"), TODAY)
    assert "Finding Norma" not in {s.title for s in screenings}


def test_german_date_and_35mm():
    screenings, _ = parse_page(fixture("calendar-1.json"), TODAY)
    s = by_title(screenings, "De cierta manera")  # dateText "So. 01.11. 17:00"
    assert s.start == datetime(2026, 11, 1, 17, 0, tzinfo=BERLIN)
    assert s.tags == ["35mm"]  # the API writes "35 mm"


def test_programme_without_credits_is_kept():
    screenings, _ = parse_page(fixture("calendar-1.json"), TODAY)
    s = by_title(screenings, "Filme von Ken Jacobs")
    assert (s.year, s.director, s.language) == (None, None, None)
    assert "Ken und Flo Jacobs" in s.series  # soft hyphen removed


def test_last_page_and_no_dialogue():
    screenings, last = parse_page(fixture("calendar-2.json"), TODAY)
    assert last
    assert by_title(screenings, "Der rote Ballon").language == "oD"


def test_parse_start_rolls_over_the_year():
    assert parse_start("Wed 13.01. 19:00", TODAY) == datetime(2027, 1, 13, 19, 0, tzinfo=BERLIN)


def test_adapter_reads_every_page():
    pages = {CALENDAR_URL.format(1): "calendar-1.json", CALENDAR_URL.format(2): "calendar-2.json"}

    class FakeFetcher:
        def get(self, url):
            return fixture(pages[url])

    programme = ArsenalAdapter().fetch(FakeFetcher())
    assert [c.id for c in programme.cinemas] == ["arsenal"]
    assert len(programme.screenings) == 4
