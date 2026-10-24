"""SQLite storage. Every scrape run is kept as a snapshot of raw screenings."""

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
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
    cinema_id TEXT NOT NULL REFERENCES cinemas(id),
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
    runtime_min INTEGER
);
CREATE INDEX IF NOT EXISTS raw_screenings_run ON raw_screenings(run_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert_cinema(conn: sqlite3.Connection, cinema: Cinema) -> None:
    conn.execute(
        "INSERT INTO cinemas VALUES (:id, :name, :address, :neighbourhood, :website) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, address=excluded.address, "
        "neighbourhood=excluded.neighbourhood, website=excluded.website",
        asdict(cinema),
    )


def start_run(conn: sqlite3.Connection, cinema_id: str) -> int:
    cur = conn.execute(
        "INSERT INTO runs (cinema_id, started_at, status) VALUES (?, ?, 'running')",
        (cinema_id, _now()),
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
        "ticket_url, language, series, tags, year, country, director, runtime_min) "
        "VALUES (:run_id, :cinema_id, :title, :start, :source_url, :ticket_url, "
        ":language, :series, :tags, :year, :country, :director, :runtime_min)",
        rows,
    )
    conn.commit()


def cinemas(conn: sqlite3.Connection) -> dict[str, Cinema]:
    rows = conn.execute("SELECT * FROM cinemas ORDER BY name").fetchall()
    return {r["id"]: Cinema(**dict(r)) for r in rows}


def last_update(conn: sqlite3.Connection) -> datetime | None:
    """When the most recent successful run finished."""
    value = conn.execute("SELECT MAX(finished_at) FROM runs WHERE status = 'ok'").fetchone()[0]
    return datetime.fromisoformat(value) if value else None


def latest_screenings(conn: sqlite3.Connection) -> list[RawScreening]:
    """Screenings from each cinema's most recent successful run."""
    rows = conn.execute(
        """
        SELECT s.* FROM raw_screenings s
        WHERE s.run_id IN (
            SELECT MAX(id) FROM runs WHERE status = 'ok' GROUP BY cinema_id
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
        )
        for r in rows
    ]
