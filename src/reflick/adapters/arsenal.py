"""Arsenal – Institut für Film und Videokunst, Plantagenstraße 30, Wedding.

The calendar page loads its events from a JSON API backed by a TYPO3 Solr
search: /api/v1/search/calendar/?tx_solr[page]=2, twelve events a page. Each
event has the credits (director, country, year, format, language version,
runtime), its series and a ticket link. The date has no year
("Sat 24.10. 17:00", or "So. 01.11. 19:00" on German pages).
"""

import json
import re
from datetime import date, datetime, time, timedelta

from reflick.adapters.base import (
    BERLIN,
    Adapter,
    Cache,
    Fetcher,
    Programme,
    clean,
    date_without_year,
    fetch_pages,
    language_code,
)
from reflick.models import Cinema, RawScreening

BASE_URL = "https://www.arsenal-berlin.de"
CALENDAR_URL = f"{BASE_URL}/api/v1/search/calendar/?tx_solr%5Bpage%5D={{}}"
DAYS_AHEAD = 180

CINEMA = Cinema(
    id="arsenal",
    name="Arsenal",
    address="Plantagenstraße 30, 13347 Berlin",
    neighbourhood="Wedding",
    website=BASE_URL,
)

DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.\s+(\d{1,2}):(\d{2})")


def _text(value: str | None) -> str | None:
    """Clean a field; the API keeps soft hyphens and line separators from the CMS."""
    return clean((value or "").replace("\xad", "")) or None


def parse_start(text: str, today: date) -> datetime:
    m = DATE_RE.search(text)
    if m is None:
        raise ValueError(f"no date in {text!r}")
    day, month, hour, minute = (int(g) for g in m.groups())
    return datetime.combine(date_without_year(day, month, today), time(hour, minute), tzinfo=BERLIN)


def parse_event(event: dict, today: date) -> RawScreening | None:
    # Events in the foyer are installations, not screenings.
    if any("foyer" in place.casefold() for place in event.get("location") or []):
        return None
    year = str(event.get("year") or "")
    runtime = re.search(r"\d+", event.get("playingTime") or "")
    film_format = _text(event.get("filmFormat"))
    return RawScreening(
        cinema_id=CINEMA.id,
        title=_text(event["title"]),
        start=parse_start(event["dateText"], today),
        source_url=BASE_URL + event["url"],
        ticket_url=event.get("salesUrl") or None,
        language=language_code(event.get("languageVersion")),
        series=_text(event.get("subtitle")),
        tags=[film_format.replace(" mm", "mm")] if film_format else [],
        year=int(year) if year.isdigit() else None,
        country=_text(event.get("country")),
        director=_text(event.get("director")),
        runtime_min=int(runtime.group()) if runtime else None,
    )


def parse_page(text: str, today: date) -> tuple[list[RawScreening], bool]:
    """One page of the calendar API: its screenings, and whether it's the last page."""
    data = json.loads(text)["content"]["colPos0"][0]["content"]["data"]["documents"]
    events = (parse_event(e, today) for e in data["list"]["results"])
    pagination = data["pagination"]
    return [e for e in events if e], pagination["current"] >= pagination["numberOfPages"]


class ArsenalAdapter(Adapter):
    id = "arsenal"

    def fetch(self, fetcher: Fetcher, cache: Cache | None = None) -> Programme:
        today = date.today()
        until = datetime.combine(today + timedelta(days=DAYS_AHEAD), time(), tzinfo=BERLIN)
        screenings = fetch_pages(
            fetcher, CALENDAR_URL.format, lambda text: parse_page(text, today), until
        )
        return Programme(cinemas=[CINEMA], screenings=screenings)
