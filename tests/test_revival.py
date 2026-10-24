from datetime import date, datetime
from zoneinfo import ZoneInfo

from reflick.models import RawScreening
from reflick.revival import is_revival

TODAY = date(2026, 10, 24)


def screening(**kwargs) -> RawScreening:
    defaults = dict(
        cinema_id="test",
        title="Some Film",
        start=datetime(2026, 10, 24, 20, 0, tzinfo=ZoneInfo("Europe/Berlin")),
        source_url="https://example.org/",
    )
    return RawScreening(**(defaults | kwargs))


def test_old_film_is_revival():
    assert is_revival(screening(year=1942), TODAY)


def test_boundary_is_five_years():
    assert is_revival(screening(year=2021), TODAY)
    assert not is_revival(screening(year=2022), TODAY)


def test_new_film_is_not_revival():
    assert not is_revival(screening(year=2025), TODAY)


def test_unknown_year_is_not_revival():
    assert not is_revival(screening(), TODAY)


def test_cinema_label_makes_new_film_a_revival():
    assert is_revival(screening(year=2024, tags=["Wiederaufführung in 4K"]), TODAY)
    assert is_revival(screening(tags=["Filmklassiker im Lichtblick-Kino"]), TODAY)
    assert is_revival(screening(series="Best of Cinema"), TODAY)
