"""Common pieces for cinema adapters."""

import re
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from reflick.models import BERLIN, Cinema, RawScreening, berlin_today  # noqa: F401 (re-exported)

# Responses worth another try: rate limiting and temporary server trouble.
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRY_PAUSE_S = 120.0
# With contact details, which Wikimedia requires and other sites appreciate.
USER_AGENT = "reflick/0.1 (+https://github.com/schildbuerger/reflick; revival screenings aggregator for Berlin)"


def clean(text: str) -> str:
    """Collapse whitespace, including nbsp and thin spaces."""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ").replace(" ", " ")).strip()


def language_code(text: str | None) -> str | None:
    """A language version as cinemas write it, with spellings of 'no dialogue'
    unified so the site's language filter shows one option for them."""
    text = clean(text or "")
    if text.casefold() in {"od", "ohne dialog"}:
        return "oD"
    return text or None


def date_without_year(day: int, month: int, today: date) -> date:
    """Programmes print '24.10.' without a year: take the one that puts it
    nearest after today, allowing for screenings up to two months back."""
    candidate = date(today.year, month, day)
    if candidate < today - timedelta(days=60):
        candidate = date(today.year + 1, month, day)
    return candidate


def fetch_pages(
    fetcher: Fetcher,
    page_url: Callable[[int], str],
    parse_page: Callable[[str], tuple[list[RawScreening], bool]],
    until: datetime,
    max_pages: int = 30,
) -> list[RawScreening]:
    """Screenings from a listing split into pages sorted by start time, such as
    a TYPO3 Solr search (`?tx_solr[page]=2`). `parse_page` returns a page's
    screenings and whether it was the last page. Stops at `until`, since such
    listings can run on into placeholder dates decades ahead."""
    screenings: list[RawScreening] = []
    for page in range(1, max_pages + 1):
        found, last = parse_page(fetcher.get(page_url(page)))
        screenings += [s for s in found if s.start < until]
        if last or not found or found[-1].start >= until:
            break
    return screenings


def retry_after_s(response: httpx.Response) -> float | None:
    """The wait a 429 or 503 response asks for, in seconds or as an HTTP date."""
    value = response.headers.get("Retry-After", "").strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


class Fetcher:
    """HTTP client that honours robots.txt, waits between requests and retries
    temporary failures (timeouts, 429, 5xx) after growing pauses, so a cinema's
    server having a bad moment doesn't fail the whole source."""

    def __init__(
        self,
        delay_s: float = 1.0,
        client: httpx.Client | None = None,
        retries: int = 2,
        backoff_s: float = 10.0,
    ):
        self.delay_s = delay_s
        self.retries = retries
        self.backoff_s = backoff_s  # first retry's pause, doubled for each further one
        self.client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=20,
        )
        self._robots: dict[str, RobotFileParser] = {}
        self._last_request = 0.0

    def get(self, url: str) -> str:
        if not self._allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        for attempt in range(self.retries + 1):
            last = attempt == self.retries
            pause = self.backoff_s * 2**attempt
            try:
                response = self._request(url)
            except httpx.TransportError:  # timeout, connection refused or reset
                if last:
                    raise
            else:
                if last or response.status_code not in RETRY_STATUSES:
                    response.raise_for_status()
                    return response.text
                pause = retry_after_s(response) or pause
            time.sleep(min(pause, MAX_RETRY_PAUSE_S))
        raise AssertionError("unreachable")

    def _request(self, url: str) -> httpx.Response:
        wait = self._last_request + self.delay_s - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            return self.client.get(url)
        finally:
            self._last_request = time.monotonic()

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser = RobotFileParser()
            response = self.client.get(f"{origin}/robots.txt")
            parser.parse(response.text.splitlines() if response.is_success else [])
            self._robots[origin] = parser
        return self._robots[origin].can_fetch(USER_AGENT, url)


class Cache:
    """What adapters see of reflick.db.Cache; this no-op version caches nothing."""

    def get(self, namespace: str, key: str, max_age: timedelta) -> dict | None:
        return None

    def set(self, namespace: str, key: str, value: dict) -> None:
        pass

    def film(self, source: str, key: str) -> dict | None:
        return None

    def save_film(self, source: str, key: str, credits: dict) -> None:
        pass


@dataclass
class Programme:
    """One source's result: its cinemas and their screenings."""

    cinemas: list[Cinema]
    screenings: list[RawScreening]
    warnings: list[str] = field(default_factory=list)


class Adapter(ABC):
    """Scrapes one source (a cinema, or a group like Yorck) into RawScreenings."""

    id: str

    @abstractmethod
    def fetch(self, fetcher: Fetcher, cache: Cache | None = None) -> Programme: ...
