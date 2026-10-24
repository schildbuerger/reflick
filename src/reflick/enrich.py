"""Look up listed films on Wikidata (titles) and OMDb (genres), and cache the
results in the database.

Wikidata goes first: it knows German titles, so it finds "Aguirre, der Zorn
Gottes" where OMDb doesn't, and its IMDb id then lets OMDb look up exactly
that film.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from reflick import db, wikidata
from reflick.omdb import OmdbClient, OmdbError, find_by_imdb_id, find_film
from reflick.revival import is_revival
from reflick.wikidata import WikidataClient, WikidataError

RETRY_MISSES_AFTER = timedelta(days=7)


@dataclass
class Result:
    matched: int = 0
    missed: int = 0
    cached: int = 0
    requests: int = 0
    error: str | None = None


@dataclass(frozen=True)
class FilmToLookUp:
    title: str
    director: str | None
    original_title: str | None


def films_to_look_up(conn: sqlite3.Connection, now: datetime) -> dict[tuple[str, int], FilmToLookUp]:
    """Distinct upcoming revivals with a year, keyed like film_matches."""
    films = {}
    for s in db.latest_screenings(conn):
        if s.year is None or s.start < now or not is_revival(s, now.date()):
            continue
        films.setdefault(
            (db.title_key(s.title), s.year), FilmToLookUp(s.title, s.director, s.original_title)
        )
    return films


def _is_fresh(row: sqlite3.Row | None, found: str, now: datetime, retry_misses: bool) -> bool:
    """Whether a cached lookup stands: a match always, a miss for a week."""
    if row is None:
        return False
    if row[found]:
        return True
    return not retry_misses and now - datetime.fromisoformat(row["looked_up_at"]) < RETRY_MISSES_AFTER


def enrich_titles(
    conn: sqlite3.Connection,
    client: WikidataClient,
    now: datetime | None = None,
    retry_misses: bool = False,
) -> Result:
    """Find German and original titles on Wikidata for films not cached yet."""
    now = now or datetime.now(timezone.utc)
    cached = db.film_titles(conn)
    omdb = db.film_matches(conn)
    result = Result()
    for key, film in films_to_look_up(conn, now).items():
        if _is_fresh(cached.get(key), "qid", now, retry_misses):
            result.cached += 1
            continue
        known = omdb.get(key)
        try:
            found = wikidata.find_film(
                client, film.title, key[1], film.director, film.original_title,
                imdb_id=known["imdb_id"] if known else None,
            )
        except WikidataError as exc:  # network or rate limit: keep what we have
            result.error = str(exc)
            break
        if found:
            db.save_film_titles(
                conn, film.title, key[1], found.qid, found.title_de, found.original_title, found.imdb_id
            )
            result.matched += 1
        else:
            db.save_film_titles(conn, film.title, key[1], None, None, None, None)
            result.missed += 1
    result.requests = client.requests
    return result


def enrich(
    conn: sqlite3.Connection,
    client: OmdbClient,
    now: datetime | None = None,
    retry_misses: bool = False,
) -> Result:
    """Look up films on OMDb that aren't cached yet. Misses are retried after a
    week, or now with retry_misses (e.g. after improving the matching), or as
    soon as Wikidata has found the film's IMDb id since."""
    now = now or datetime.now(timezone.utc)
    cached = db.film_matches(conn)
    titles = db.film_titles(conn)
    result = Result()
    for key, film in films_to_look_up(conn, now).items():
        row, wiki = cached.get(key), titles.get(key)
        imdb_id = wiki["imdb_id"] if wiki else None
        # A miss found on Wikidata since gets another try right away.
        new_id = imdb_id and row and not row["imdb_id"] and wiki["looked_up_at"] > row["looked_up_at"]
        if _is_fresh(row, "imdb_id", now, retry_misses) and not new_id:
            result.cached += 1
            continue
        try:
            # Wikidata already checked year and director, so its id is trusted.
            match = find_by_imdb_id(client, imdb_id) if imdb_id else None
            if match is None:
                original = film.original_title or (wiki["original_title"] if wiki else None)
                match = find_film(client, film.title, key[1], film.director, original)
        except OmdbError as exc:  # bad key or daily limit: keep what we have
            result.error = str(exc)
            break
        if match:
            db.save_film_match(conn, film.title, key[1], match.imdb_id, match.title, match.genres)
            result.matched += 1
        else:
            db.save_film_match(conn, film.title, key[1], None, None, [])
            result.missed += 1
    result.requests = client.requests
    return result
