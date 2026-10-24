"""Babylon Mitte, Rosa-Luxemburg-Straße 30 (not Yorck's Babylon Kreuzberg).

The site has no structured data, but /programm lists every upcoming screening
on one page as `<li class="mix ...">`, one per showing:

- `data-date="2026-10-24 15:45:00"`: start time, with the year
- class `cat-<CATEGORY>`: the series or category (FILM, CLOCKWORK-KUBRICK ...)
- classes `tag-<slug>`: extras such as english-ov, english-subtitles, stummfilm
- `.right-mix`: the full title, a credit line and the runtime. The credit line
  is cut off with "…" after about 100 characters, so for entries where that
  hides the year, the adapter also reads the film's own page.

Theatre shows and readings are listed too and are skipped.
"""

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from reflick.adapters.base import BERLIN, Adapter, Cache, Fetcher, Programme, clean
from reflick.models import Cinema, RawScreening

BASE_URL = "https://babylonberlin.eu"
PROGRAMME_URL = f"{BASE_URL}/programm"

CINEMA = Cinema(
    id="babylon",
    name="Babylon Mitte",  # Yorck runs a separate "Babylon Kreuzberg"
    address="Rosa-Luxemburg-Straße 30, 10178 Berlin",
    neighbourhood="Mitte",
    website=BASE_URL,
)

LANGUAGE_RE = re.compile(r"\b(OmeU|OmenglU|OmdU|OmU|OV|OF|DF)\b")
# A bracket in the title naming the version, e.g. "[OmU, English with German Subt.]".
LANGUAGE_BRACKET_RE = re.compile(r"\s*[\[(][^\])]*\b(?:OmeU|OmenglU|OmdU|OmU|OV|OF|DF)\b[^\])]*[\])]")
# Fallback when the credit line names no version.
TAG_LANGUAGES = {"english-ov": "OV", "english-subtitles": "OmeU"}
# Entries with these tags are stage shows or readings, not screenings.
NON_FILM_TAGS = {"theater", "literatur", "konzerte"}
# Country, then year, then a comma or the end, e.g. "[OV] USA, 1955, R: ...",
# "ITA/D/Schw 2013, R: ..." or "BRD 1972, R:…".
COUNTRY_YEAR_RE = re.compile(
    r"(?:^|[\]\),])\s*([^,\[\]()]*?)[,\s]+((?:18|19|20)\d{2})\b(?=\s*(?:,|…|$))"
)
DIRECTOR_RE = re.compile(r"\bR:\s*([^,…]+?)(?:\s+(?:mit|with)\b|,|…|$)")


def _norm(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold())


def split_series(title: str, names: list[str]) -> tuple[str, str | None]:
    """'Clockwork Kubrick: Spartacus' -> ('Spartacus', 'Clockwork Kubrick').

    The prefix only counts as a series if it matches the entry's category or
    one of its tags, so titles like 'Kinski 100!: Aguirre, der Zorn Gottes'
    split but a film whose own title contains a colon doesn't.
    """
    prefix, sep, rest = title.partition(": ")
    if not sep or not rest:
        return title, None
    p = _norm(prefix)
    for name in names:
        n = _norm(name)
        if n and (p.startswith(n) or n.startswith(p)):
            return rest, prefix
    return title, None


def parse_credits(text: str) -> dict:
    text = clean(text)
    facts: dict = {}
    if m := COUNTRY_YEAR_RE.search(text):
        facts["country"] = m.group(1).strip() or None
        facts["year"] = int(m.group(2))
    if m := DIRECTOR_RE.search(text):
        facts["director"] = m.group(1).strip()
    return facts


def clean_title(text: str) -> str:
    title = clean(text).replace("`", "'")
    title = LANGUAGE_BRACKET_RE.sub("", title)
    title = LANGUAGE_RE.sub("", title)
    return clean(title).strip(" -")


def _category(li: Tag) -> str | None:
    link = li.select_one(".right-mix .mix-category a")
    return clean(link.get_text()) if link else None


def parse_entry(li: Tag, series_names: list[str]) -> RawScreening | None:
    """One `li.mix`. `series_names` are all categories on the page, so a series
    prefix is recognised even on entries filed under plain FILM."""
    block = li.select_one(".right-mix")
    title_link = block.select_one("a.mix-title") if block else None
    if title_link is None or not li.get("data-date"):
        return None

    classes = li.get("class", [])
    tags = [c.removeprefix("tag-") for c in classes if c.startswith("tag-")]
    if NON_FILM_TAGS & set(tags):
        return None
    category = _category(li)
    title, series = split_series(clean_title(title_link.get_text()), [*series_names, *tags])

    intro_node = block.select_one(".mix-introtext")
    intro = clean(intro_node.get_text()) if intro_node else ""
    lang_match = LANGUAGE_RE.search(intro)
    language = lang_match.group(1) if lang_match else next(
        (TAG_LANGUAGES[t] for t in tags if t in TAG_LANGUAGES), None
    )
    runtime_node = block.select_one(".runtime")
    runtime = re.search(r"\d+", runtime_node.get_text()) if runtime_node else None

    facts = parse_credits(intro)
    return RawScreening(
        cinema_id=CINEMA.id,
        title=title,
        start=datetime.fromisoformat(li["data-date"]).replace(tzinfo=BERLIN),
        source_url=urljoin(BASE_URL, title_link["href"]),
        language=language,
        series=series,
        tags=[t for t in [category, *tags] if t],
        runtime_min=int(runtime.group()) if runtime else None,
        **facts,
    )


def parse_programme(html: str) -> list[RawScreening]:
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select("li.mix")
    generic = {"FILM", "LIVE EVENT", "ORCHESTER"}
    series_names = sorted({c for li in items if (c := _category(li)) and c not in generic})
    entries = (parse_entry(li, series_names) for li in items)
    return [e for e in entries if e is not None]


def parse_film_page(html: str) -> dict:
    """Credits from a film's own page: the lines above its description."""
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("[itemprop=articleBody]")
    if body is None:
        return {}
    lines = []
    for line in body.get_text("\n").splitlines():
        line = clean(line)
        if line in {"EN", "DE"}:  # the description starts here
            break
        if line:
            lines.append(line)
    text = " ".join(lines)
    facts = parse_credits(text)
    if m := LANGUAGE_RE.search(text):
        facts["language"] = m.group(1)
    return facts


class BabylonAdapter(Adapter):
    id = "babylon"

    def fetch(self, fetcher: Fetcher, cache: Cache | None = None) -> Programme:
        screenings = parse_programme(fetcher.get(PROGRAMME_URL))
        # Fill in credits the programme's cut-off text hides, one request per film.
        details: dict[str, dict] = {}
        for s in screenings:
            if s.year is not None:
                continue
            if s.source_url not in details:
                details[s.source_url] = parse_film_page(fetcher.get(s.source_url))
            for key, value in details[s.source_url].items():
                if key == "language" or getattr(s, key) is None:
                    setattr(s, key, value)
        return Programme(cinemas=[CINEMA], screenings=screenings)
