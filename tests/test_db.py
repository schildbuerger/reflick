from datetime import datetime
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
