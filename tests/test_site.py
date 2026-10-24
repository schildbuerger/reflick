from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from reflick import db, site
from reflick.adapters.lichtblick import CINEMA, parse_film_page

FIXTURES = Path(__file__).parent / "fixtures" / "lichtblick"
BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=BERLIN)


def seeded_db(tmp_path):
    conn = db.connect(tmp_path / "test.sqlite")
    db.upsert_cinema(conn, CINEMA)
    screenings = []
    for name in ["casablanca", "invisible-people", "trainspotting", "united-trash"]:
        html = (FIXTURES / f"{name}.html").read_text(encoding="utf-8")
        screenings += parse_film_page(html, f"https://lichtblick-kino.org/{name}/", date(2026, 10, 24))
    run = db.start_run(conn, CINEMA.id)
    db.save_screenings(conn, run, screenings)
    db.finish_run(conn, run, "ok")
    return conn


def test_build_writes_index_film_pages_and_calendar(tmp_path):
    out = tmp_path / "site"
    count = site.build(seeded_db(tmp_path), out, now=NOW)

    # Invisible People (2025) is not a revival and must be left out.
    assert count == 3
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "Casablanca" in index
    assert "Invisible People" not in index
    # Casablanca starts at 00:00 on Sunday but is listed as Saturday 24:00.
    saturday = index.split("Saturday 24 October")[1].split("Sunday 25 October")[0]
    assert "Casablanca" in saturday
    assert ">24:00</time>" in saturday
    assert 'href="film/casablanca-1942/"' in index
    assert "Wiederaufführung in 4K" in index

    film = (out / "film" / "casablanca-1942" / "index.html").read_text(encoding="utf-8")
    assert "Michael Curtiz" in film
    assert 'href="../../"' in film

    ics = (out / "reflick.ics").read_bytes().decode()
    assert ics.count("BEGIN:VEVENT") == 3
    assert "SUMMARY:Casablanca (1942)\r\n" in ics
    assert "DTSTART:20261024T220000Z" in ics  # 00:00 CEST on 25 Oct
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))


def test_rebuild_removes_pages_of_films_no_longer_listed(tmp_path):
    out = tmp_path / "site"
    conn = seeded_db(tmp_path)
    site.build(conn, out, now=NOW)
    stale = out / "film" / "old-film-1950"
    stale.mkdir()
    site.build(conn, out, now=NOW)
    assert not stale.exists()


def test_past_screenings_are_not_listed(tmp_path):
    later = datetime(2026, 10, 26, 12, 0, tzinfo=BERLIN)
    assert site.build(seeded_db(tmp_path), tmp_path / "site", now=later) == 0


def test_slugify_strips_accents_and_punctuation():
    assert site.slugify("Ausländer raus! Schlingensiefs Container 2002") == (
        "auslander-raus-schlingensiefs-container-2002"
    )
