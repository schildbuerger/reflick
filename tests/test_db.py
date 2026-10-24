import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from reflick import db
from reflick.adapters.lichtblick import CINEMA
from reflick.models import RawScreening


def make(title: str) -> RawScreening:
    return RawScreening(
        cinema_id=CINEMA.id,
        title=title,
        start=datetime(2026, 10, 24, 20, 0, tzinfo=ZoneInfo("Europe/Berlin")),
        source_url="https://lichtblick-kino.org/x/",
        tags=["Spielfilm"],
        year=1942,
    )


def test_latest_screenings_use_last_ok_run(tmp_path):
    conn = db.connect(tmp_path / "test.sqlite")
    db.upsert_cinema(conn, CINEMA)

    old = db.start_run(conn, CINEMA.id)
    db.save_screenings(conn, old, [make("Old")])
    db.finish_run(conn, old, "ok")

    new = db.start_run(conn, CINEMA.id)
    db.save_screenings(conn, new, [make("New")])
    db.finish_run(conn, new, "ok")

    broken = db.start_run(conn, CINEMA.id)
    db.finish_run(conn, broken, "failed", "boom")

    [s] = db.latest_screenings(conn)
    assert s == make("New")


def test_prune_keeps_recent_runs_and_each_sources_latest_ok_run(tmp_path):
    conn = db.connect(tmp_path / "test.sqlite")
    db.upsert_cinema(conn, CINEMA)

    def run(source, status, days_ago):
        run_id = db.start_run(conn, source)
        db.save_screenings(conn, run_id, [make(f"{source}-{days_ago}")])
        db.finish_run(conn, run_id, status)
        started = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        conn.execute("UPDATE runs SET started_at = ? WHERE id = ?", (started, run_id))
        conn.commit()
        return run_id

    old_ok = run("lichtblick", "ok", 60)
    old_failed = run("lichtblick", "failed", 50)
    recent_ok = run("lichtblick", "ok", 2)
    only_ok_of_other_source = run("babylon", "ok", 40)  # stale, but still its newest data

    assert db.prune_runs(conn, keep=timedelta(days=28)) == 2
    remaining = {row[0] for row in conn.execute("SELECT id FROM runs")}
    assert remaining == {recent_ok, only_ok_of_other_source}
    assert old_ok not in remaining and old_failed not in remaining
    orphans = conn.execute(
        "SELECT COUNT(*) FROM raw_screenings WHERE run_id NOT IN (SELECT id FROM runs)"
    ).fetchone()[0]
    assert orphans == 0


def test_cache_expires(tmp_path):
    cache = db.Cache(db.connect(tmp_path / "test.sqlite"))
    cache.set("yorck-film", "angel-heart", {"year": 1987})
    assert cache.get("yorck-film", "angel-heart", timedelta(days=30)) == {"year": 1987}
    assert cache.get("yorck-film", "angel-heart", timedelta(0)) is None
    assert cache.get("yorck-film", "other", timedelta(days=30)) is None


def test_old_database_is_migrated(tmp_path):
    path = tmp_path / "old.sqlite"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE runs (id INTEGER PRIMARY KEY, cinema_id TEXT NOT NULL,
            started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL, error TEXT);
        CREATE TABLE raw_screenings (id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL,
            cinema_id TEXT NOT NULL, title TEXT NOT NULL, start TEXT NOT NULL,
            source_url TEXT NOT NULL, ticket_url TEXT, language TEXT, series TEXT,
            tags TEXT NOT NULL, year INTEGER, country TEXT, director TEXT, runtime_min INTEGER);
        INSERT INTO runs VALUES (1, 'lichtblick', '2026-10-24T09:00:00+00:00',
            '2026-10-24T09:01:00+00:00', 'ok', NULL);
        INSERT INTO raw_screenings (run_id, cinema_id, title, start, source_url, tags, year)
            VALUES (1, 'lichtblick', 'Casablanca', '2026-10-24T20:00:00+02:00', 'https://x/', '[]', 1942);
    """)
    old.close()

    conn = db.connect(path)
    [s] = db.latest_screenings(conn)
    assert (s.title, s.original_title) == ("Casablanca", None)
    db.start_run(conn, "yorck")  # the renamed column works for new runs
