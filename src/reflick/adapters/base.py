"""Common pieces for cinema adapters."""

import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

import httpx

from reflick.models import Cinema, RawScreening

USER_AGENT = "reflick/0.1 (+revival screenings aggregator for Berlin)"
BERLIN = ZoneInfo("Europe/Berlin")


def clean(text: str) -> str:
    """Collapse whitespace, including nbsp and thin spaces."""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ").replace(" ", " ")).strip()


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
