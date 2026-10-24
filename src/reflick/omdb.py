"""Film lookup on OMDb (https://www.omdbapi.com/) for genres and IMDb ids.

OMDb knows English and original titles, not German distribution titles, and
gives the US release year (Casablanca: 1943), so matching allows a year off by
one and checks the director whenever the cinema names one.

The API key is passed as a query parameter, which is how OMDb works. Errors
are re-raised without the request URL so the key never ends up in logs.
"""

import re
import time
import unicodedata
from dataclasses import dataclass, field

import httpx

from reflick.titles import split_addons

API_URL = "https://www.omdbapi.com/"
MAX_SEARCH_CANDIDATES = 3


class OmdbError(RuntimeError):
    """The API is unusable (bad key, daily limit, network). Stop looking up."""


@dataclass
class Match:
    imdb_id: str
    title: str
    year: int | None
    director: str | None
    genres: list[str] = field(default_factory=list)


class OmdbClient:
    def __init__(self, api_key: str, delay_s: float = 0.1, client: httpx.Client | None = None):
        self.api_key = api_key
        self.delay_s = delay_s
        self.client = client or httpx.Client(timeout=20)
        self.requests = 0

    def query(self, **params) -> dict | None:
        """One API call. Returns None for 'not found', raises OmdbError otherwise."""
        if self.requests:
            time.sleep(self.delay_s)
        self.requests += 1
        try:
            response = self.client.get(API_URL, params={"apikey": self.api_key, **params})
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # `from None`: the original exception carries the URL with the key.
            raise OmdbError(f"OMDb request failed ({type(exc).__name__})") from None
        if data.get("Response") == "True":
            return data
        error = data.get("Error", "")
        # "Too many results" answers a search for a very short title: no usable match.
        if "not found" in error.lower() or "too many results" in error.lower():
            return None
        raise OmdbError(f"OMDb: {error}")


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


def _surnames(names: str) -> set[str]:
    """'Moritz Enders und Gunther Merz' -> {'enders', 'merz'}."""
    parts = re.split(r",|&|\band\b|\bund\b|\bu\.", names)
    return {words[-1] for p in parts if (words := _fold(p).split())}


def director_matches(cinema: str | None, omdb: str | None) -> bool:
    """True unless both name directors and no surname overlaps."""
    if not cinema or not omdb or omdb == "N/A":
        return True
    return bool(_surnames(cinema) & _surnames(omdb))


def _year(value: str | None) -> int | None:
    m = re.match(r"\d{4}", value or "")
    return int(m.group()) if m else None


def _match(data: dict) -> Match:
    genre = data.get("Genre") or ""
    return Match(
        imdb_id=data["imdbID"],
        title=data.get("Title", ""),
        year=_year(data.get("Year")),
        director=data.get("Director") if data.get("Director") != "N/A" else None,
        genres=[g.strip() for g in genre.split(",") if g.strip() and genre != "N/A"],
    )


def title_variants(title: str) -> list[str]:
    """Titles to search for, most likely first: without the cinema's add-ons
    (see reflick.titles), then looser guesses that are only tried on OMDb and
    never shown, since a match still has to pass the year and director check.

    'Modern Times LIVE mit Babylon Orchester Berlin' -> ['Modern Times', ...]
    "Chaplin's The Gold Rush with LIVE Orchestra" -> [..., 'The Gold Rush']
    """
    base, _ = split_addons(title)
    variants = [base] if base == title else [base, title]
    cuts = [
        r"\s+-\s+.*$",  # "Nordstream - Die Sprengung" -> "Nordstream"
        r"^\w+'s\s+",  # "Chaplin's The Gold Rush"
        r"^[^:]+:\s+",  # "Huang Shuqin: Woman Demon Human"
    ]
    for pattern in cuts:
        for v in list(variants):
            if (cut := re.sub(pattern, "", v).strip(" :-")) and cut not in variants:
                variants.append(cut)
    for v in list(variants):
        if (tight := re.sub(r"\s*/\s*", "/", v)) not in variants:
            variants.append(tight)
    return variants


def _acceptable(m: Match, year: int, director: str | None) -> bool:
    if m.year is None or abs(m.year - year) > 1:
        return False
    if director and not m.director:
        # Entries without a director are mostly making-ofs, shorts or podcast
        # episodes that share the title ("El laberinto del fauno: Detrás de...").
        return False
    return director_matches(director, m.director)


def find_by_imdb_id(client: OmdbClient, imdb_id: str) -> Match | None:
    data = client.query(i=imdb_id)
    return _match(data) if data else None


def find_film(
    client: OmdbClient,
    title: str,
    year: int,
    director: str | None,
    original_title: str | None = None,
) -> Match | None:
    """original_title, when the cinema gives one, is tried first: OMDb knows
    'The Apartment', not the German 'Das Appartement'."""
    variants = title_variants(original_title) if original_title else []
    variants += [v for v in title_variants(title) if v not in variants]
    for variant in variants:
        # Best guess by exact title; its year may be the US release year.
        if (data := client.query(t=variant, type="movie")) and _acceptable(
            m := _match(data), year, director
        ):
            return m
        # Otherwise search that year and check the top candidates' details.
        found = client.query(s=variant, y=year, type="movie")
        for candidate in (found or {}).get("Search", [])[:MAX_SEARCH_CANDIDATES]:
            if (data := client.query(i=candidate["imdbID"])) and _acceptable(
                m := _match(data), year, director
            ):
                return m
    return None
