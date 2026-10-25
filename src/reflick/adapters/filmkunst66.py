"""filmkunst 66, Bleibtreustr. 12, Charlottenburg.

The site shows its programme only in kinoheld's booking widget, which
kinoheld's terms don't let us read (see docs/roadmap.md). But the programme
page also links the cinema's own weekly flyer, a PDF with a table per screen:

                                     DO         FR         SA     ...  MI
     Adams Acht                        14:45      14:45      14:45
     Heimsuchung – Eine                17:15      17:15      17:15
     Jahrhundertgeschichte             20:00      20:00      20:00
     Ein Haufen toller Hunde (1965)                                     20:30

pypdf's layout mode keeps the columns, so each time belongs to the weekday
heading above it, and the heading "Donnerstag, 22.10. – Mittwoch, 28.10.26"
dates the week. A title can run over two lines ("Heimsuchung – Eine /
Jahrhundertgeschichte"), and a line with times but no title is another row
of screenings of the film above. The flyer covers the current week only.
"""

import io
import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

from pypdf import PdfReader

from reflick.adapters.base import BERLIN, Adapter, Cache, Fetcher, Programme, clean, language_code
from reflick.models import Cinema, RawScreening

BASE_URL = "https://filmkunst66.de/"
PROGRAMME_URL = urljoin(BASE_URL, "programm")
FLYER_RE = re.compile(r'href="([^"]*Wochenflyer[^"]*\.pdf)"')

CINEMA = Cinema(
    id="filmkunst66",
    name="Filmkunst 66",
    address="Bleibtreustr. 12, 10623 Berlin",
    neighbourhood="Charlottenburg",
    website=BASE_URL,
    lat=52.5044,
    lon=13.3197,  # from OpenStreetMap
)

WEEK_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.\s*[–-]\s*\w+,\s*(\d{1,2})\.(\d{1,2})\.(\d{2,4})")
WEEKDAYS = ["DO", "FR", "SA", "SO", "MO", "DI", "MI"]  # the week runs Thursday to Wednesday
HEADER_RE = re.compile(r"\s*" + r"\s+".join(WEEKDAYS) + r"\s*")
TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
# A title line ending in one of these goes on in the next line.
RUNS_ON = {"der", "die", "das", "den", "dem", "des", "ein", "eine", "einer", "eines", "und", "&",
           "the", "of", "and", "a", "–", "-", ":"}
LANGUAGE_RE = re.compile(r"(DF|OV|OF|OmU|OmeU|OmdU|OmdeU)!?")
PARENTHESES_RE = re.compile(r"\s*\(([^()]*)\)$")
YEAR_RE = re.compile(r"(?:18|19|20)\d{2}")


def week_start(text: str) -> date:
    """The Thursday the flyer's week starts on."""
    m = WEEK_RE.search(text)
    if m is None:
        raise ValueError("no week dates in the flyer")
    d1, m1, d2, m2, y2 = (int(x) for x in m.groups())
    year = y2 + 2000 if y2 < 100 else y2
    return date(year - 1 if m1 > m2 else year, m1, d1)  # a week can span New Year


def split_title(title: str) -> tuple[str, int | None, str | None]:
    """Year and language version from a closing bracket. 'Sense and Sensibility
    (2026, OmU)' -> ('Sense and Sensibility', 2026, 'OmU'); a bracket holding just
    the year stays, as titles at other cinemas do: 'Lola Montès (1955)'."""
    m = PARENTHESES_RE.search(title)
    if m is None:
        return title, None, None
    parts = [p.strip() for p in m.group(1).split(",")]
    year = next((int(p) for p in parts if YEAR_RE.fullmatch(p)), None)
    language = next((lm.group(1) for p in parts if (lm := LANGUAGE_RE.fullmatch(p))), None)
    if language is None and year is None:
        return title, None, None
    return (title[: m.start()] if language else title), year, language


def _runs_on(previous: str, line_title: str, has_times: bool) -> bool:
    """Whether a title line continues the title of the line above."""
    if not has_times:
        return True  # "Haus" under "Frau Winkler verlässt das"
    words = previous.split()
    return line_title.startswith("(") or line_title[:1].islower() or bool(words and words[-1].casefold() in RUNS_ON)


def parse_flyer(text: str) -> list[RawScreening]:
    first_day = week_start(text)
    films: list[dict] = []  # {"title": str, "times": [(day, hour, minute)]}
    columns: list[float] | None = None
    blank_before = True
    for line in text.split("\n"):
        if HEADER_RE.fullmatch(line):
            columns = [m.start() + len(m.group()) / 2 for m in re.finditer(r"\S+", line)]
            blank_before = True
            continue
        if columns is None:
            continue
        if line.startswith("NEU:") or "Min. FSK" in line:
            break  # the film descriptions follow the tables
        if not line.strip() or "(Saal" in line:
            blank_before = True
            continue
        times = list(TIME_RE.finditer(line))
        title = clean(line[: times[0].start()] if times else line)
        if title and films and not blank_before and _runs_on(films[-1]["title"], title, bool(times)):
            films[-1]["title"] += " " + title
        elif title:
            films.append({"title": title, "times": []})
        if films:
            for m in times:
                centre = (m.start() + m.end()) / 2
                day = min(range(len(columns)), key=lambda i: abs(columns[i] - centre))
                films[-1]["times"].append((day, int(m.group(1)), int(m.group(2))))
        blank_before = False
    screenings = []
    for film in films:
        title, year, language = split_title(film["title"])
        for day, hour, minute in film["times"]:
            start = datetime.combine(first_day + timedelta(days=day), datetime.min.time()).replace(
                hour=hour, minute=minute, tzinfo=BERLIN
            )
            screenings.append(RawScreening(
                cinema_id=CINEMA.id,
                title=title,
                start=start,
                source_url=PROGRAMME_URL,
                language=language_code(language),
                year=year,
            ))
    return sorted(screenings, key=lambda s: s.start)


def pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text(extraction_mode="layout") for page in reader.pages)


class Filmkunst66Adapter(Adapter):
    id = "filmkunst66"

    def fetch(self, fetcher: Fetcher, cache: Cache | None = None) -> Programme:
        page = fetcher.get(PROGRAMME_URL)
        flyers = dict.fromkeys(urljoin(BASE_URL, href) for href in FLYER_RE.findall(page))
        warnings = [] if flyers else ["no weekly flyer linked on the programme page"]
        screenings: list[RawScreening] = []
        for url in flyers:  # at a week's change there can be two
            screenings += parse_flyer(pdf_text(fetcher.get_bytes(url)))
        unique = {(s.title, s.start): s for s in screenings}
        return Programme(cinemas=[CINEMA], screenings=list(unique.values()), warnings=warnings)
