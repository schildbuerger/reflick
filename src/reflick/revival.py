"""The rule that decides whether a screening counts as a revival."""

from datetime import date

from reflick.models import RawScreening

MIN_AGE_YEARS = 5

# Labels cinemas use for re-releases; matched case-insensitively as substrings.
REVIVAL_KEYWORDS = (
    "wiederaufführung",
    "klassiker",
    "reprise",
    "restauriert",
    "restaurierung",
    "best of cinema",
    "re-release",
)


def revival_labels(screening: RawScreening) -> list[str]:
    """The series name and tags that mark the screening as a re-release."""
    texts = [screening.series or "", *screening.tags]
    return [t for t in texts if any(kw in t.lower() for kw in REVIVAL_KEYWORDS)]


def has_revival_label(screening: RawScreening) -> bool:
    title = screening.title.lower()
    return bool(revival_labels(screening)) or any(kw in title for kw in REVIVAL_KEYWORDS)


def is_revival(screening: RawScreening, today: date | None = None, year: int | None = None) -> bool:
    """A film at least MIN_AGE_YEARS old, or one the cinema labels a re-release.
    `year` overrides the cinema's year, e.g. with Wikidata's for a matched film."""
    if has_revival_label(screening):
        return True
    year = year or screening.year
    if year is None:
        return False
    today = today or date.today()
    return today.year - year >= MIN_AGE_YEARS
