"""Lichtblick-Kino, Kastanienallee 77, Prenzlauer Berg.

The site has no structured data. /programm/ links every current film; each
film page carries the credits line ("USA 1942, 102 min, Regie: ...") and the
full list of showtimes with kinoheld ticket ids.
"""

import re
from datetime import date, datetime, time, timedelta

from bs4 import BeautifulSoup, Tag

from reflick.adapters.base import (
    BERLIN,
    Adapter,
    Cache,
    Fetcher,
    Programme,
    berlin_today,
    clean,
    date_without_year,
)
from reflick.models import Cinema, RawScreening

BASE_URL = "https://lichtblick-kino.org"
PROGRAMME_URL = f"{BASE_URL}/programm/"
TICKET_URL = "https://www.kinoheld.de/kino/berlin/lichtblick-kino-berlin/show/{id}"

CINEMA = Cinema(
    id="lichtblick",
    name="Lichtblick-Kino",
    address="Kastanienallee 77, 10435 Berlin",
    neighbourhood="Prenzlauer Berg",
    website=BASE_URL,
    lat=52.5365,
    lon=13.4078,  # from OpenStreetMap
)


def parse_programme(html: str) -> list[str]:
    """Film page URLs linked from the programme page, in order, deduplicated."""
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for link in soup.select("#filmliste .eintrag > a[href]"):
        url = link["href"]
        if url.startswith(BASE_URL) and url not in urls:
            urls.append(url)
    return urls


DIRECTOR_RE = re.compile(
    # Label may name combined roles ("Regie & Kamera :", "Regie und Kamera:").
    r"\b(?:Regie|Director|Directed by)[^:,;]*:\s*"
    r"(.+?)"
    r"(?:[,;]\s*(?:mit|Cast|Buch|Drehbuch|Kamera|Musik|Produktion)\b|;|$)"
)


def parse_credits(text: str) -> dict:
    """Parse e.g. 'USA 1942, 102 min, Regie: Michael Curtiz, mit ...'.

    Variants seen: a leading genre ('Dokumentarfilm, D 2020, ...'), English
    labels ('Director: Danny Boyle, Cast: ...') and ';' as separator.
    """
    text = clean(text)
    facts: dict = {}
    # Country is the part of the comma-separated field right before the year.
    if m := re.search(r"(?:^|,)\s*([^,]*?)\s*\b((?:18|19|20)\d{2})\b", text):
        facts["country"] = m.group(1) or None
        facts["year"] = int(m.group(2))
    if m := re.search(r"(\d+)\s*min\b", text):
        facts["runtime_min"] = int(m.group(1))
    if m := DIRECTOR_RE.search(text):
        facts["director"] = m.group(1).strip(" ,")
    return facts


def infer_date(day_month: str, today: date) -> date:
    """'24.10.' has no year."""
    day, month = (int(p) for p in day_month.strip(". ").split("."))
    return date_without_year(day, month, today)


def parse_start(day_month: str, hhmm: str, today: date) -> datetime:
    hour, minute = (int(p) for p in clean(hhmm).split(":"))
    # The site writes midnight as 24:00 on the previous day.
    day = infer_date(day_month, today) + timedelta(days=hour // 24)
    return datetime.combine(day, time(hour % 24, minute), tzinfo=BERLIN)


def _title(node: Tag) -> str:
    for omu in node.select("span.omu"):
        omu.decompose()
    for br in node.select("br"):
        br.replace_with(" ")
    return clean(node.get_text())


def parse_film_page(html: str, url: str, today: date) -> list[RawScreening]:
    soup = BeautifulSoup(html, "html.parser")
    film = soup.select_one("#programm .film")
    if film is None:  # series overview or event page, no showtimes of its own
        return []

    # Films in a series have two title blocks: the series ("filmreihe") first,
    # then the film itself.
    title_node = film.select_one(".titelblock:not(.filmreihe) .titel")
    if title_node is None:
        return []
    title = _title(title_node)
    series_node = film.select_one(".titelblock.filmreihe .titel")
    series = clean(series_node.get_text()) if series_node else None

    tags = [
        clean(n.get_text())
        for n in film.select(
            ".titelblock .genre, .titelblock .uebertitel_klein, "
            ".titelblock .subtitel_klein"
        )
    ]
    credits_node = film.select_one(".film_credits")
    facts = parse_credits(credits_node.get_text()) if credits_node else {}

    screenings = []
    for row in film.select(".termine .zeile"):
        date_node = row.select_one(".datum")
        time_node = row.select_one(".uhrzeit")
        if date_node is None or time_node is None:
            continue
        lang_node = row.select_one(".info_omu")
        ticket = row.select_one(".tickets[data-ticket]")
        screenings.append(
            RawScreening(
                cinema_id=CINEMA.id,
                title=title,
                start=parse_start(date_node.get_text(), time_node.get_text(), today),
                source_url=url,
                ticket_url=TICKET_URL.format(id=ticket["data-ticket"]) if ticket else None,
                language=clean(lang_node.get_text()) or None if lang_node else None,
                series=series,
                tags=tags,
                **facts,
            )
        )
    return screenings


class LichtblickAdapter(Adapter):
    id = "lichtblick"

    def fetch(self, fetcher: Fetcher, cache: Cache | None = None) -> Programme:
        today = berlin_today()
        screenings: list[RawScreening] = []
        for url in parse_programme(fetcher.get(PROGRAMME_URL)):
            screenings.extend(parse_film_page(fetcher.get(url), url, today))
        return Programme(cinemas=[CINEMA], screenings=screenings)
