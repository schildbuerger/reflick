"""Shared data types.

Adapters emit `RawScreening`s exactly as the cinema publishes them. Matching
them to a canonical film (TMDB/Wikidata) is a later step and gets its own
types, so raw data can be reprocessed when matching improves.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")


def berlin_today() -> date:
    """Today's date in Berlin, whatever the machine's timezone (CI runs in UTC)."""
    return datetime.now(BERLIN).date()


@dataclass(frozen=True)
class Cinema:
    id: str  # stable slug, e.g. "lichtblick"
    name: str
    address: str
    neighbourhood: str
    website: str


@dataclass
class RawScreening:
    cinema_id: str
    title: str  # as printed by the cinema, without language suffix
    start: datetime  # timezone-aware, Europe/Berlin
    source_url: str  # page the screening was scraped from
    ticket_url: str | None = None
    language: str | None = None  # OV, OmU, OmeU, DF ...
    series: str | None = None  # e.g. a retrospective or "Filmklassiker"
    tags: list[str] = field(default_factory=list)  # cinema labels, genre
    # Film facts as stated by the cinema, if any.
    year: int | None = None
    country: str | None = None
    director: str | None = None
    runtime_min: int | None = None
    original_title: str | None = None  # e.g. "The Apartment" for "Das Appartement"
