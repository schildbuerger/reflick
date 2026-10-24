"""Hackesche Höfe Kino, Rosenthaler Straße 40/41, Mitte.

A TYPO3 site without structured data. /programm-tickets/aktuelles-programm/
links every film with screenings, including the 35mm and DEFA specials; its
grid only covers the current week, so the showtimes come from the film pages.
A film page has the credits ("AB 12 JAHREN / 106 MINUTEN / OmeU",
"Bundesrepublik Deutschland 1987", "Regie: ...") and every showtime with a
kinoheld ticket link. Showtime dates have no year ("Freitag 30. Oktober").
"""

import re
from datetime import date, datetime, time

from bs4 import BeautifulSoup

from reflick.adapters.base import (
    BERLIN,
    Adapter,
    Cache,
    Fetcher,
    Programme,
    clean,
    date_without_year,
)
from reflick.models import Cinema, RawScreening

BASE_URL = "https://www.hoefekino.de"
PROGRAMME_URL = f"{BASE_URL}/programm-tickets/aktuelles-programm/"
TICKET_URL = "https://www.kinoheld.de/kino/berlin/hackesche-hoefe-kino?mode=widget&showId={id}"

CINEMA = Cinema(
    id="hoefe",
    name="Hackesche Höfe Kino",
    address="Rosenthaler Straße 40/41, 10178 Berlin",
    neighbourhood="Mitte",
    website=BASE_URL,
)

MONTHS = {
    name: i
    for i, name in enumerate(
        "Januar Februar März April Mai Juni Juli August September Oktober November Dezember".split(),
        start=1,
    )
}
DATE_RE = re.compile(rf"(\d{{1,2}})\.\s*({'|'.join(MONTHS)})")
# The label under the title names a series ("35mm-Kinospecial: Klaus Kinski
# zum 100. Geburtstag") or is just a note: an age or language hint, a dated
# preview ("Preview am 1. November um 11 Uhr!") or an award.
NOTE_RE = re.compile(rf"^(?:Altersempfehlung|Sprachfassung)|preis|\d{{1,2}}\.\s*(?:{'|'.join(MONTHS)})", re.I)


def parse_programme(html: str) -> list[str]:
    """Film page URLs linked from the programme page, in order, deduplicated."""
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for link in soup.select('#main a[href^="/filme/"]'):
        url = BASE_URL + link["href"].split("#")[0]
        if url not in urls:
            urls.append(url)
    return urls


def parse_facts(lines: list[str]) -> dict:
    """Parse 'AB 12 JAHREN / 106 MINUTEN / OmeU' and 'Bundesrepublik Deutschland 1987'."""
    facts: dict = {}
    for line in lines:
        if m := re.search(r"(\d+)\s*MINUTEN", line, re.I):
            facts["runtime_min"] = int(m.group(1))
        elif m := re.fullmatch(r"(.*?)\s*\b((?:18|19|20)\d{2})", line):
            facts["country"] = m.group(1) or None
            facts["year"] = int(m.group(2))
    return facts


def infer_date(text: str, today: date) -> date:
    """'Freitag 30. Oktober' has no year."""
    m = DATE_RE.search(text)
    if m is None:
        raise ValueError(f"no date in {text!r}")
    return date_without_year(int(m.group(1)), MONTHS[m.group(2)], today)


def parse_film_page(html: str, url: str, today: date) -> list[RawScreening]:
    soup = BeautifulSoup(html, "html.parser")
    film = soup.select_one(".programme-details")
    if film is None:
        return []
    title = clean(film.select_one(".programme-details-title h2").get_text())

    label_node = film.select_one(".programme-details-title-label")
    label = clean(label_node.get_text()) if label_node else ""
    series = label if label and not NOTE_RE.search(label) else None
    tags = ["35mm"] if label.startswith("35mm") else []

    facts = parse_facts(
        [clean(n.get_text()) for n in film.select(".programme-details-info-additional span")]
    )
    for p in film.select(".programme-details-info-description-text p"):
        if m := re.match(r"Regie:\s*(.+)", clean(p.get_text())):
            facts["director"] = re.sub(r"\s+,", ",", m.group(1))

    screenings = []
    for item in film.select(".programme-details-showtimes-item"):
        day = infer_date(item.select_one(".programme-details-showtimes-item-date").get_text(" "), today)
        # Only showtimes with a language note have the "language-showtime" class.
        for show in item.select(".movie-item-showtime a"):
            hour, minute = (int(p) for p in clean(show.select_one(".movie-itemshowtime-linktext").get_text()).split(":"))
            lang_node = show.select_one(".movie-item-showing-language")
            screenings.append(
                RawScreening(
                    cinema_id=CINEMA.id,
                    title=title,
                    start=datetime.combine(day, time(hour, minute), tzinfo=BERLIN),
                    source_url=url,
                    ticket_url=TICKET_URL.format(id=show["data-showid"]) if show.get("data-showid") else None,
                    language=clean(lang_node.get_text()) or None if lang_node else None,
                    series=series,
                    tags=tags,
                    **facts,
                )
            )
    return screenings


class HoefeAdapter(Adapter):
    id = "hoefe"

    def fetch(self, fetcher: Fetcher, cache: Cache | None = None) -> Programme:
        today = date.today()
        screenings: list[RawScreening] = []
        for url in parse_programme(fetcher.get(PROGRAMME_URL)):
            screenings.extend(parse_film_page(fetcher.get(url), url, today))
        return Programme(cinemas=[CINEMA], screenings=screenings)
