"""Common pieces for cinema adapters."""

import re
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

import httpx

from reflick.models import Cinema, RawScreening

# With contact details, which Wikimedia requires and other sites appreciate.
USER_AGENT = "reflick/0.1 (+https://github.com/schildbuerger/reflick; revival screenings aggregator for Berlin)"
BERLIN = ZoneInfo("Europe/Berlin")


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
    fetcher: "Fetcher",
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


class Fetcher:
    """HTTP client that honours robots.txt and waits between requests."""

    def __init__(self, delay_s: float = 1.0, client: httpx.Client | None = None):
        self.delay_s = delay_s
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
        wait = self._last_request + self.delay_s - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        response = self.client.get(url)
        self._last_request = time.monotonic()
        response.raise_for_status()
        return response.text

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
