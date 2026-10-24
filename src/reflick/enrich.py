"""Look up listed films on OMDb and cache the results in the database."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from reflick import db
from reflick.omdb import OmdbClient, OmdbError, find_film
from reflick.revival import is_revival

RETRY_MISSES_AFTER = timedelta(days=7)


@dataclass
class Result:
    matched: int = 0
    missed: int = 0
    cached: int = 0
    requests: int = 0
    error: str | None = None


def films_to_look_up(conn: sqlite3.Connection, now: datetime) -> dict[tuple[str, int], tuple[str, str | None]]:
    """Distinct upcoming revivals with a year: key -> (title, director)."""
    films = {}
    for s in db.latest_screenings(conn):
        if s.year is None or s.start < now or not is_revival(s, now.date()):
            continue
        films.setdefault((db.title_key(s.title), s.year), (s.title, s.director))
    return films


def enrich(
    conn: sqlite3.Connection,
    client: OmdbClient,
    now: datetime | None = None,
    retry_misses: bool = False,
) -> Result:
    """Look up films not cached yet. Misses are retried after a week, or now
    with retry_misses (e.g. after improving the matching)."""
    now = now or datetime.now(timezone.utc)
    cached = db.film_matches(conn)
    result = Result()
    for key, (title, director) in films_to_look_up(conn, now).items():
        row = cached.get(key)
        if row and (
            row["imdb_id"]
            or (
                not retry_misses
                and now - datetime.fromisoformat(row["looked_up_at"]) < RETRY_MISSES_AFTER
            )
        ):
            result.cached += 1
            continue
        try:
            match = find_film(client, title, key[1], director)
        except OmdbError as exc:  # bad key or daily limit: keep what we have
            result.error = str(exc)
            break
        if match:
            db.save_film_match(conn, title, key[1], match.imdb_id, match.title, match.genres)
            result.matched += 1
        else:
            db.save_film_match(conn, title, key[1], None, None, [])
            result.missed += 1
    result.requests = client.requests
    return result
