import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from reflick import db, site
from reflick.adapters.lichtblick import CINEMA, parse_film_page
from reflick.models import Cinema, RawScreening

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
    assert "Michael Curtiz" in index
    assert "Wiederaufführung in 4K" in index
    # Titles link to the film's page on the cinema's site; no ticket links.
    # A "Details" button at the end of the row opens the cinema's film page;
    # the title itself is plain text.
    assert (
        '<a class="details" role="button" href="https://lichtblick-kino.org/casablanca/"'
        in index
    )
    assert "<h3>Casablanca</h3>" in index
    assert "kinoheld" not in index
    assert not (out / "film").exists()
    # The cinema name links to Google Maps, with a pin icon in front.
    maps = (
        "https://www.google.com/maps/search/?api=1&amp;query="
        "Lichtblick-Kino%2C+Kastanienallee+77%2C+10435+Berlin"
    )
    assert f'<a class="cinema secondary" href="{maps}"' in index
    assert '<svg class="pin"' in index
    assert '@click="reset()"' in index

    ics = (out / "reflick.ics").read_bytes().decode()
    assert ics.count("BEGIN:VEVENT") == 3
    assert "SUMMARY:Casablanca (1942)\r\n" in ics
    assert "DTSTART:20261024T220000Z" in ics  # 00:00 CEST on 25 Oct
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))


def test_single_page_lists_screenings_across_cinemas(tmp_path):
    conn = seeded_db(tmp_path)
    other = Cinema("other", "Other Kino", "Somewhere 1, Berlin", "Mitte", "https://other.example/")
    db.upsert_cinema(conn, other)
    run = db.start_run(conn, other.id)
    db.save_screenings(conn, run, [
        RawScreening(
            cinema_id=other.id,
            title="Metropolis",
            start=datetime(2026, 10, 24, 19, 0, tzinfo=BERLIN),
            source_url="https://other.example/metropolis",
            year=1927,
        )
    ])
    db.finish_run(conn, run, "ok")

    out = tmp_path / "site"
    assert site.build(conn, out, now=NOW) == 4
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "Metropolis" in index and "Casablanca" in index
    assert '<option value="other">Other Kino</option>' in index
    assert '<option value="lichtblick">Lichtblick-Kino</option>' in index
    # One checkbox per district that has screenings, in alphabetical order.
    districts = re.findall(r'<input type="checkbox" value="([^"]+)" x-model="districts">', index)
    assert districts == ["Mitte", "Prenzlauer Berg"]
    assert '"district": "Mitte"' in index


def test_genres_from_omdb_are_shown_and_filterable(tmp_path):
    conn = seeded_db(tmp_path)
    db.save_film_match(conn, "Casablanca", 1942, "tt0034583", "Casablanca", ["Drama", "Romance"])
    db.save_film_match(conn, "Trainspotting", 1996, None, None, [])  # looked up, no match
    out = tmp_path / "site"
    site.build(conn, out, now=NOW)
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "Michael Curtiz · 102 min · Drama, Romance" in index
    assert '<option value="Romance">Romance</option>' in index
    assert '"genres": ["Drama", "Romance"]' in index


def test_title_addons_become_badges_and_verified_title_is_shown(tmp_path):
    conn = db.connect(tmp_path / "test.sqlite")
    db.upsert_cinema(conn, CINEMA)
    run = db.start_run(conn, CINEMA.id)
    db.save_screenings(conn, run, [
        RawScreening(
            cinema_id=CINEMA.id,
            title="Chaplin's The Gold Rush with LIVE Orchestra",
            start=datetime(2026, 10, 24, 20, 0, tzinfo=BERLIN),
            source_url="https://x/",
            year=1925,
        )
    ])
    db.finish_run(conn, run, "ok")
    db.save_film_match(
        conn, "Chaplin's The Gold Rush with LIVE Orchestra", 1925, "tt0015864", "The Gold Rush", []
    )
    out = tmp_path / "site"
    site.build(conn, out, now=NOW)
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "<h3>The Gold Rush</h3>" in index
    assert '<span class="badge label">Live Orchestra</span>' in index
    assert "SUMMARY:The Gold Rush (1925)" in (out / "reflick.ics").read_text(encoding="utf-8")


def test_past_screenings_are_not_listed(tmp_path):
    later = datetime(2026, 10, 26, 12, 0, tzinfo=BERLIN)
    assert site.build(seeded_db(tmp_path), tmp_path / "site", now=later) == 0
