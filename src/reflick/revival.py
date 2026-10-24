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


def has_revival_label(screening: RawScreening) -> bool:
    texts = [screening.title, screening.series or "", *screening.tags]
    return any(kw in t.lower() for t in texts for kw in REVIVAL_KEYWORDS)


def is_revival(screening: RawScreening, today: date | None = None) -> bool:
    """A film at least MIN_AGE_YEARS old, or one the cinema labels a re-release."""
    if has_revival_label(screening):
        return True
    if screening.year is None:
        return False
    today = today or date.today()
    return today.year - screening.year >= MIN_AGE_YEARS
