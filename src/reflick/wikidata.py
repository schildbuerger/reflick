"""Find films on Wikidata for their German title, original title and IMDb id.

Uses the Action API (www.wikidata.org/w/api.php). Its robots.txt disallows
/w/ for crawlers, but Wikimedia's robot policy (https://w.wiki/4wJS) has
explicit rules for using the API: one request at a time, fewer than five a
second, batched where possible, and a User-Agent with contact details. This
is the one place reflick doesn't go through the robots.txt-checking Fetcher;
the SPARQL query service, which robots.txt also disallows, isn't used.

A film is found by full-text search over all labels and aliases, so German
("Das Appartement"), original ("La règle du jeu") and English titles all
work. A candidate must share a release year (±1) with the cinema's year and,
when the cinema names one, a director's surname. When OMDb already knows the
film's IMDb id, the item is looked up by that id instead. The earliest
publication date is the film's release year, used for the revival rule.
"""

import re
import time
from dataclasses import dataclass, field

import httpx

from reflick.adapters.base import USER_AGENT, clean
from reflick.omdb import director_matches
from reflick.titles import split_addons

API_URL = "https://www.wikidata.org/w/api.php"
MAX_CANDIDATES = 5
# Properties: P57 director, P345 IMDb id, P577 publication date, P1476 title.


class WikidataError(RuntimeError):
    """The API is unusable (network, rate limit). Stop looking up."""


@dataclass
class WikiFilm:
    qid: str
    title_de: str | None  # the German label, i.e. the German release title
    original_title: str | None
    imdb_id: str | None
    years: list[int] = field(default_factory=list)  # every publication date's year, sorted
    director_ids: list[str] = field(default_factory=list)


class WikidataClient:
    def __init__(self, delay_s: float = 1.0, client: httpx.Client | None = None):
        self.delay_s = delay_s
        self.client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}, timeout=20
        )
        self.requests = 0

    def query(self, **params) -> dict:
        if self.requests:
            time.sleep(self.delay_s)
        self.requests += 1
        try:
            response = self.client.get(API_URL, params={"format": "json", "formatversion": 2, **params})
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise WikidataError(f"Wikidata request failed ({type(exc).__name__})") from None
        if "error" in data:
            raise WikidataError(f"Wikidata: {data['error'].get('info', data['error'])}")
        return data

    def search(self, text: str) -> list[str]:
        """Item ids whose labels or aliases match, best first."""
        data = self.query(
            action="query", list="search", srsearch=text, srnamespace=0,
            srlimit=MAX_CANDIDATES, srprop="",
        )
        return [hit["title"] for hit in data["query"]["search"]]

    def entities(self, ids: list[str], props: str, languages: str) -> dict[str, dict]:
        data = self.query(action="wbgetentities", ids="|".join(ids), props=props, languages=languages)
        return data["entities"]


def _statements(entity: dict, prop: str) -> list:
    """A property's values, preferred ones first and deprecated ones left out."""
    statements = [s for s in entity.get("claims", {}).get(prop, []) if s.get("rank") != "deprecated"]
    statements.sort(key=lambda s: s.get("rank") != "preferred")
    return [v for s in statements if (v := s["mainsnak"].get("datavalue", {}).get("value"))]


def parse_film(entity: dict) -> WikiFilm:
    titles = _statements(entity, "P1476")
    imdb = [v for v in _statements(entity, "P345") if v.startswith("tt")]
    return WikiFilm(
        qid=entity["id"],
        title_de=entity.get("labels", {}).get("de", {}).get("value"),
        original_title=titles[0]["text"] if titles else None,
        imdb_id=imdb[0] if imdb else None,
        years=sorted({int(v["time"][1:5]) for v in _statements(entity, "P577")}),
        director_ids=[v["id"] for v in _statements(entity, "P57")],
    )


def film_by_id(client: WikidataClient, qid: str) -> WikiFilm | None:
    entity = client.entities([qid], "labels|claims", "de").get(qid)
    return parse_film(entity) if entity and "claims" in entity else None


def search_text(title: str) -> str:
    """A title as a search query: without the cinema's add-ons and without
    characters CirrusSearch treats as operators."""
    base, _ = split_addons(title)
    return clean(re.sub(r'["~*?\\]|(?<!\S)-', " ", base))


def find_film(
    client: WikidataClient,
    title: str,
    year: int,
    director: str | None,
    original_title: str | None = None,
    imdb_id: str | None = None,
) -> WikiFilm | None:
    if imdb_id:
        # OMDb already identified the film, so no checks are needed.
        ids = client.search(f"haswbstatement:P345={imdb_id}")
        if ids:
            return parse_film(client.entities(ids[:1], "labels|claims", "de")[ids[0]])
    queries = [search_text(t) for t in (original_title, title) if t]
    for query in dict.fromkeys(q for q in queries if q):
        ids = client.search(f"{query} haswbstatement:P57")  # works with a director: films, mostly
        if not ids:
            continue
        entities = client.entities(ids, "labels|claims", "de")
        films = [parse_film(entities[q]) for q in ids if q in entities]
        candidates = [f for f in films if any(abs(y - year) <= 1 for y in f.years)]
        if candidates and director:
            names = _director_names(client, candidates)
            candidates = [
                c for c in candidates
                if director_matches(director, ", ".join(names.get(d, "") for d in c.director_ids))
            ]
        if candidates:
            return candidates[0]
    return None


def _director_names(client: WikidataClient, films: list[WikiFilm]) -> dict[str, str]:
    """Directors' names by item id, in one request for all candidates."""
    ids = list(dict.fromkeys(d for f in films for d in f.director_ids))
    if not ids:
        return {}
    entities = client.entities(ids, "labels", "de|en|mul")
    return {
        q: next((label["value"] for label in e.get("labels", {}).values()), "")
        for q, e in entities.items()
    }
