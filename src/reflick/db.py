"""SQLite storage. Every scrape run is kept as a snapshot of raw screenings.

A run belongs to a source (one adapter), which may cover several cinemas,
e.g. all Yorck cinemas come from the "yorck" source.
"""

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from reflick.models import Cinema, RawScreening

SCHEMA = """
CREATE TABLE IF NOT EXISTS cinemas (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    neighbourhood TEXT NOT NULL,
    website TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,  -- adapter id
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,  -- running | ok | empty | failed
    error TEXT
);
CREATE TABLE IF NOT EXISTS raw_screenings (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    cinema_id TEXT NOT NULL REFERENCES cinemas(id),
    title TEXT NOT NULL,
    start TEXT NOT NULL,
    source_url TEXT NOT NULL,
    ticket_url TEXT,
    language TEXT,
    series TEXT,
    tags TEXT NOT NULL,  -- JSON list
    year INTEGER,
    country TEXT,
    director TEXT,
    runtime_min INTEGER,
    original_title TEXT
);
CREATE INDEX IF NOT EXISTS raw_screenings_run ON raw_screenings(run_id);
-- Parsed detail pages adapters don't need to fetch every day (e.g. film credits).
CREATE TABLE IF NOT EXISTS page_cache (
    namespace TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,  -- JSON
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (namespace, key)
);
-- OMDb lookups by (casefolded title, cinema's year). imdb_id is NULL when
-- nothing matched; such misses are retried after a while.
CREATE TABLE IF NOT EXISTS film_matches (
    title_key TEXT NOT NULL,
    year INTEGER NOT NULL,
    imdb_id TEXT,
    matched_title TEXT,
    genres TEXT NOT NULL,  -- JSON list
    looked_up_at TEXT NOT NULL,
    PRIMARY KEY (title_key, year)
);
-- Wikidata lookups, keyed like film_matches. qid is NULL when nothing matched.
CREATE TABLE IF NOT EXISTS film_titles (
    title_key TEXT NOT NULL,
    year INTEGER NOT NULL,
    qid TEXT,
    title_de TEXT,
    original_title TEXT,
    imdb_id TEXT,
    looked_up_at TEXT NOT NULL,
    PRIMARY KEY (title_key, year)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring databases created by earlier versions up to SCHEMA."""
    if "cinema_id" in _columns(conn, "runs"):  # runs were per cinema before Yorck
        conn.execute("ALTER TABLE runs RENAME COLUMN cinema_id TO source")
    if "original_title" not in _columns(conn, "raw_screenings"):
        conn.execute("ALTER TABLE raw_screenings ADD COLUMN original_title TEXT")
    conn.commit()


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


class Cache:
    """JSON values by (namespace, key), e.g. ("yorck-film", slug) -> credits."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get(self, namespace: str, key: str, max_age: timedelta) -> dict | None:
        row = self.conn.execute(
            "SELECT value, fetched_at FROM page_cache WHERE namespace = ? AND key = ?",
            (namespace, key),
        ).fetchone()
        if row is None:
            return None
        age = datetime.now(timezone.utc) - datetime.fromisoformat(row["fetched_at"])
        return json.loads(row["value"]) if age < max_age else None

    def set(self, namespace: str, key: str, value: dict) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO page_cache VALUES (?, ?, ?, ?)",
            (namespace, key, json.dumps(value, ensure_ascii=False), _now()),
        )
        self.conn.commit()


def upsert_cinema(conn: sqlite3.Connection, cinema: Cinema) -> None:
    conn.execute(
        "INSERT INTO cinemas VALUES (:id, :name, :address, :neighbourhood, :website) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, address=excluded.address, "
        "neighbourhood=excluded.neighbourhood, website=excluded.website",
        asdict(cinema),
    )


def start_run(conn: sqlite3.Connection, source: str) -> int:
    cur = conn.execute(
        "INSERT INTO runs (source, started_at, status) VALUES (?, ?, 'running')",
        (source, _now()),
    )
    conn.commit()
    return cur.lastrowid


def finish_run(
    conn: sqlite3.Connection, run_id: int, status: str, error: str | None = None
) -> None:
    conn.execute(
        "UPDATE runs SET finished_at = ?, status = ?, error = ? WHERE id = ?",
        (_now(), status, error, run_id),
    )
    conn.commit()


def save_screenings(
    conn: sqlite3.Connection, run_id: int, screenings: list[RawScreening]
) -> None:
    rows = []
    for s in screenings:
        row = asdict(s)
        row["run_id"] = run_id
        row["start"] = s.start.isoformat()
        row["tags"] = json.dumps(s.tags, ensure_ascii=False)
        rows.append(row)
    conn.executemany(
        "INSERT INTO raw_screenings (run_id, cinema_id, title, start, source_url, "
        "ticket_url, language, series, tags, year, country, director, runtime_min, "
        "original_title) "
        "VALUES (:run_id, :cinema_id, :title, :start, :source_url, :ticket_url, "
        ":language, :series, :tags, :year, :country, :director, :runtime_min, "
        ":original_title)",
        rows,
    )
    conn.commit()


def prune_runs(conn: sqlite3.Connection, keep: timedelta) -> int:
    """Delete runs (and their screenings) older than `keep`, except each
    source's latest successful run, which the site is built from. Also drops
    page cache entries long past use. Returns the number of runs removed."""
    now = datetime.now(timezone.utc)
    cutoff = (now - keep).isoformat()
    old = [
        row[0]
        for row in conn.execute(
            """
            SELECT id FROM runs
            WHERE started_at < ?
              AND id NOT IN (SELECT MAX(id) FROM runs WHERE status = 'ok' GROUP BY source)
            """,
            (cutoff,),
        )
    ]
    marks = ",".join("?" * len(old))
    if old:
        conn.execute(f"DELETE FROM raw_screenings WHERE run_id IN ({marks})", old)
        conn.execute(f"DELETE FROM runs WHERE id IN ({marks})", old)
    conn.execute(
        "DELETE FROM page_cache WHERE fetched_at < ?", ((now - timedelta(days=90)).isoformat(),)
    )
    conn.commit()
    conn.execute("VACUUM")  # actually shrink the file, which the CI cache stores
    return len(old)


def title_key(title: str) -> str:
    return " ".join(title.casefold().split())


def film_matches(conn: sqlite3.Connection) -> dict[tuple[str, int], sqlite3.Row]:
    rows = conn.execute("SELECT * FROM film_matches").fetchall()
    return {(r["title_key"], r["year"]): r for r in rows}


def save_film_match(
    conn: sqlite3.Connection,
    title: str,
    year: int,
    imdb_id: str | None,
    matched_title: str | None,
    genres: list[str],
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO film_matches VALUES (?, ?, ?, ?, ?, ?)",
        (title_key(title), year, imdb_id, matched_title,
         json.dumps(genres, ensure_ascii=False), _now()),
    )
    conn.commit()


def film_titles(conn: sqlite3.Connection) -> dict[tuple[str, int], sqlite3.Row]:
    rows = conn.execute("SELECT * FROM film_titles").fetchall()
    return {(r["title_key"], r["year"]): r for r in rows}


def save_film_titles(
    conn: sqlite3.Connection,
    title: str,
    year: int,
    qid: str | None,
    title_de: str | None,
    original_title: str | None,
    imdb_id: str | None,
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO film_titles VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title_key(title), year, qid, title_de, original_title, imdb_id, _now()),
    )
    conn.commit()


@dataclass(frozen=True)
class FilmInfo:
    """What OMDb and Wikidata confirmed about a film."""

    title: str | None  # OMDb's (mostly English) title
    genres: list[str]
    imdb_id: str | None = None
    title_de: str | None = None  # from Wikidata
    original_title: str | None = None  # from Wikidata


def film_info(conn: sqlite3.Connection) -> dict[tuple[str, int], FilmInfo]:
    """Films matched on OMDb or Wikidata, keyed like film_matches."""
    omdb = {k: r for k, r in film_matches(conn).items() if r["imdb_id"]}
    wiki = {k: r for k, r in film_titles(conn).items() if r["qid"]}
    info = {}
    for key in omdb.keys() | wiki.keys():
        o, w = omdb.get(key), wiki.get(key)
        info[key] = FilmInfo(
            title=o["matched_title"] if o else None,
            genres=json.loads(o["genres"]) if o else [],
            imdb_id=(o and o["imdb_id"]) or (w and w["imdb_id"]) or None,
            title_de=w["title_de"] if w else None,
            original_title=w["original_title"] if w else None,
        )
    return info


def cinemas(conn: sqlite3.Connection) -> dict[str, Cinema]:
    rows = conn.execute("SELECT * FROM cinemas ORDER BY name").fetchall()
    return {r["id"]: Cinema(**dict(r)) for r in rows}


def last_update(conn: sqlite3.Connection) -> datetime | None:
    """When the most recent successful run finished."""
    value = conn.execute("SELECT MAX(finished_at) FROM runs WHERE status = 'ok'").fetchone()[0]
    return datetime.fromisoformat(value) if value else None


def latest_screenings(conn: sqlite3.Connection) -> list[RawScreening]:
    """Screenings from each source's most recent successful run."""
    rows = conn.execute(
        """
        SELECT s.* FROM raw_screenings s
        WHERE s.run_id IN (
            SELECT MAX(id) FROM runs WHERE status = 'ok' GROUP BY source
        )
        ORDER BY s.start
        """
    ).fetchall()
    return [
        RawScreening(
            cinema_id=r["cinema_id"],
            title=r["title"],
            start=datetime.fromisoformat(r["start"]),
            source_url=r["source_url"],
            ticket_url=r["ticket_url"],
            language=r["language"],
            series=r["series"],
            tags=json.loads(r["tags"]),
            year=r["year"],
            country=r["country"],
            director=r["director"],
            runtime_min=r["runtime_min"],
            original_title=r["original_title"],
        )
        for r in rows
    ]
