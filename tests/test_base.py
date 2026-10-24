from datetime import date, datetime, timedelta

import pytest

from reflick.adapters.base import BERLIN, date_without_year, fetch_pages, language_code
from reflick.models import RawScreening

TODAY = date(2026, 10, 24)


@pytest.mark.parametrize(
    "day, month, expected",
    [
        (30, 10, date(2026, 10, 30)),
        (13, 1, date(2027, 1, 13)),
        (1, 9, date(2026, 9, 1)),  # recent past stays this year
        (2, 3, date(2027, 3, 2)),
    ],
)
def test_date_without_year(day, month, expected):
    assert date_without_year(day, month, TODAY) == expected


@pytest.mark.parametrize(
    "text, expected",
    [("Ohne Dialog", "oD"), ("ohne Dialog", "oD"), ("oD", "oD"), (" OmU ", "OmU"), ("", None), (None, None)],
)
def test_language_code(text, expected):
    assert language_code(text) == expected


def screening(day: int) -> RawScreening:
    start = datetime(2026, 10, 24, 20, 0, tzinfo=BERLIN) + timedelta(days=day)
    return RawScreening(cinema_id="x", title=f"Film {day}", start=start, source_url="u")


class PagedFetcher:
    """Page n holds the screenings 10 days apart; page 4 is the last."""

    def __init__(self):
        self.requested: list[int] = []

    def get(self, url: str) -> str:
        page = int(url)
        self.requested.append(page)
        return url

    @staticmethod
    def parse(text: str) -> tuple[list[RawScreening], bool]:
        page = int(text)
        return [screening(10 * (page - 1) + i) for i in range(0, 10, 5)], page == 4


def test_fetch_pages_reads_until_the_last_page():
    fetcher = PagedFetcher()
    until = datetime(2027, 1, 1, tzinfo=BERLIN)
    found = fetch_pages(fetcher, str, PagedFetcher.parse, until)
    assert fetcher.requested == [1, 2, 3, 4]
    assert len(found) == 8


def test_fetch_pages_stops_at_the_date_limit():
    fetcher = PagedFetcher()
    until = datetime(2026, 11, 7, tzinfo=BERLIN)  # page 2 runs from day 10 to day 15
    found = fetch_pages(fetcher, str, PagedFetcher.parse, until)
    assert fetcher.requested == [1, 2]
    assert [s.title for s in found] == ["Film 0", "Film 5", "Film 10"]
