from datetime import date, datetime, timedelta

import httpx
import pytest

from reflick.adapters import base
from reflick.adapters.base import BERLIN, Fetcher, date_without_year, fetch_pages, language_code
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


def fetcher_for(responses: list, pauses: list[float], monkeypatch) -> tuple[Fetcher, list[str]]:
    """A Fetcher whose server answers with `responses` in turn (an int is a
    status, an exception is raised); robots.txt is missing. Pauses are recorded."""
    requested: list[str] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        requested.append(str(request.url))
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, httpx.Response):
            return answer
        return httpx.Response(answer, text=f"status {answer}")

    monkeypatch.setattr(base.time, "sleep", pauses.append)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return Fetcher(delay_s=0, client=client, backoff_s=10), requested


def test_fetcher_retries_server_errors_with_growing_pauses(monkeypatch):
    pauses: list[float] = []
    fetcher, requested = fetcher_for([503, 502, 200], pauses, monkeypatch)
    assert fetcher.get("https://cinema.example/programm") == "status 200"
    assert len(requested) == 3
    assert pauses == [10, 20]


def test_fetcher_retries_timeouts(monkeypatch):
    pauses: list[float] = []
    fetcher, _ = fetcher_for([httpx.ReadTimeout("slow"), 200], pauses, monkeypatch)
    assert fetcher.get("https://cinema.example/programm") == "status 200"
    assert pauses == [10]


def test_fetcher_honours_retry_after(monkeypatch):
    pauses: list[float] = []
    busy = httpx.Response(429, headers={"Retry-After": "42"})
    fetcher, _ = fetcher_for([busy, 200], pauses, monkeypatch)
    fetcher.get("https://cinema.example/programm")
    assert pauses == [42]


def test_fetcher_gives_up_after_its_retries(monkeypatch):
    pauses: list[float] = []
    fetcher, requested = fetcher_for([500, 500, 500], pauses, monkeypatch)
    with pytest.raises(httpx.HTTPStatusError):
        fetcher.get("https://cinema.example/programm")
    assert len(requested) == 3

    fetcher, _ = fetcher_for([httpx.ConnectError("refused")] * 3, [], monkeypatch)
    with pytest.raises(httpx.ConnectError):
        fetcher.get("https://cinema.example/programm")


def test_fetcher_does_not_retry_client_errors(monkeypatch):
    pauses: list[float] = []
    fetcher, requested = fetcher_for([404], pauses, monkeypatch)
    with pytest.raises(httpx.HTTPStatusError):
        fetcher.get("https://cinema.example/gone")
    assert (len(requested), pauses) == (1, [])


def test_fetcher_keeps_no_cookies(monkeypatch):
    sent: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        sent.append(request.headers.get("cookie"))
        # A session cookie with a non-ASCII name, as Sinema Transtopia sends.
        return httpx.Response(200, text="ok", headers=[(b"set-cookie", "si\u0307_session=abc; Path=/".encode())])

    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    fetcher = Fetcher(delay_s=0, client=base.http_client(transport=httpx.MockTransport(handler)))
    fetcher.get("https://cinema.example/calendar")
    fetcher.get("https://cinema.example/film")
    assert sent == [None, None]


def test_fetcher_get_bytes(monkeypatch):
    pdf = b"%PDF-1.7 \xe2\x80\x93 binary"
    fetcher, _ = fetcher_for([httpx.Response(200, content=pdf)], [], monkeypatch)
    assert fetcher.get_bytes("https://cinema.example/flyer.pdf") == pdf
