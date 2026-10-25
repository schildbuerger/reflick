import json
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from reflick import db, site
from reflick.adapters.lichtblick import CINEMA, parse_film_page
from reflick.models import Cinema, RawScreening

FIXTURES = Path(__file__).parent / "fixtures" / "lichtblick"
BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=BERLIN)


def checkboxes(index: str, model: str) -> list[str]:
    """Values of a multi-select filter's checkboxes, in page order."""
    return re.findall(rf'<input type="checkbox" value="([^"]+)" x-model="{model}">', index)


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
    assert """x-text="dayLabel('2026-10-24', 'Saturday, 24. October')">Saturday, 24. October</h2>""" in index
    saturday = index.split(">Saturday, 24. October</h2>")[1].split(">Sunday, 25. October</h2>")[0]
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
    # Every filter is a multi-select: one checkbox per value that occurs, sorted.
    assert checkboxes(index, "cinemas") == ["lichtblick", "other"]
    assert checkboxes(index, "districts") == ["Mitte", "Prenzlauer Berg"]
    assert checkboxes(index, "languages") == ["OmeU", "OV"]  # "engl. OV" is OV
    assert "<select" not in index
    assert '"district": "Mitte"' in index
    assert '"other": "Other Kino"' in index  # names for the closed cinema dropdown's label


def test_genres_from_omdb_are_shown_and_filterable(tmp_path):
    conn = seeded_db(tmp_path)
    db.save_film_match(conn, "Casablanca", 1942, "tt0034583", "Casablanca", ["Drama", "Romance"])
    db.save_film_match(conn, "Trainspotting", 1996, None, None, [])  # looked up, no match
    out = tmp_path / "site"
    site.build(conn, out, now=NOW)
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "Michael Curtiz · 102 min · Drama, Romance" in index
    # Matched films link to Letterboxd via their IMDb id; unmatched ones don't.
    assert 'href="https://letterboxd.com/imdb/tt0034583/"' in index
    assert index.count('class="letterboxd"') == 1
    assert checkboxes(index, "genres") == ["Drama", "Romance"]
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


def test_build_serves_assets_itself_and_writes_legal_pages(tmp_path):
    out = tmp_path / "site"
    site.build(seeded_db(tmp_path), out, now=NOW)
    index = (out / "index.html").read_text(encoding="utf-8")
    # No third-party requests: Pico and Alpine come from the site itself.
    assert "cdn.jsdelivr.net" not in index
    assert 'href="static/pico.min.css"' in index and 'src="static/alpine.min.js"' in index
    assert (out / "static" / "pico.min.css").stat().st_size > 10_000
    assert (out / "static" / "alpine.min.js").stat().st_size > 10_000
    # The logo, in the header and as the favicon.
    assert (out / "static" / "logo.svg").exists()
    assert '<img src="static/logo.svg" alt="">reflick</a>' in index
    assert '<link rel="icon" href="static/logo.svg" type="image/svg+xml">' in index
    assert 'href="impressum.html"' in index and 'href="datenschutz.html"' in index
    impressum = (out / "impressum.html").read_text(encoding="utf-8")
    assert '<html lang="de">' in impressum
    # The shipped templates are placeholders, and the build points that out.
    placeholders = site.unfilled_placeholders(out)
    assert set(placeholders) == {"impressum.html", "datenschutz.html"}
    assert "[[E-Mail-Adresse]]" in placeholders["impressum.html"]


def test_day_name_format():
    assert site.day_name(date(2026, 10, 24)) == "Saturday, 24. October"
    assert site.day_name(date(2026, 11, 1)) == "Sunday, 1. November"
    assert site.short_day(date(2026, 10, 24)) == "Sat 24. Oct"


def test_date_strip_has_a_chip_per_day_with_screenings(tmp_path):
    out = tmp_path / "site"
    site.build(seeded_db(tmp_path), out, now=NOW)
    index = (out / "index.html").read_text(encoding="utf-8")
    # Casablanca at 24:00 on Saturday counts for Saturday, not Sunday.
    assert re.findall(r'class="chip" data-day="([\d-]+)"', index) == ["2026-10-24", "2026-10-25"]
    assert ">Sat 24. Oct</span>" in index
    assert "All dates" in index


def test_past_screenings_are_not_listed(tmp_path):
    later = datetime(2026, 10, 26, 12, 0, tzinfo=BERLIN)
    assert site.build(seeded_db(tmp_path), tmp_path / "site", now=later) == 0


def test_omdb_year_decides_for_matched_films(tmp_path):
    conn = seeded_db(tmp_path)
    # The cinema says 1995, OMDb 2024 (made up): too recent, so it's left out.
    db.save_film_match(conn, "United Trash", 1995, "tt0118025", "United Trash", [], 900, 2024)
    out = tmp_path / "site"
    assert site.build(conn, out, now=NOW) == 2
    assert "United Trash" not in (out / "index.html").read_text(encoding="utf-8")
    # Matched, but OMDb has no year: the cinema's year stands.
    db.save_film_match(conn, "United Trash", 1995, "tt0118025", "United Trash", [], 900, 0)
    assert site.build(conn, out, now=NOW) == 3
    # A re-release label counts whatever the year.
    db.save_film_match(conn, "Trainspotting", 1996, "tt0117951", "Trainspotting", [], 9_999, 2024)
    assert site.build(conn, out, now=NOW) == 3


def test_rows_carry_start_times_for_hiding_started_screenings(tmp_path):
    out = tmp_path / "site"
    site.build(seeded_db(tmp_path), out, now=NOW)
    index = (out / "index.html").read_text(encoding="utf-8")
    rows = json.loads(re.search(r'<script type="application/json" id="rows">(.*?)</script>', index).group(1))
    starts = re.findall(r'<time datetime="([^"]+)"', index)
    assert [r["start"] for r in rows] == [int(datetime.fromisoformat(s).timestamp() * 1000) for s in starts]


def test_popularity_levels_are_filterable_best_known_first(tmp_path):
    conn = seeded_db(tmp_path)
    db.save_film_match(conn, "Casablanca", 1942, "tt0034583", "Casablanca", [], 632_401)
    db.save_film_match(conn, "Trainspotting", 1996, "tt0117951", "Trainspotting", [], 9_999)
    # United Trash isn't matched: its popularity is unknown, not rare.
    out = tmp_path / "site"
    site.build(conn, out, now=NOW)
    index = (out / "index.html").read_text(encoding="utf-8")
    assert checkboxes(index, "popularity") == ["well-known", "rare", "unknown"]
    rows = json.loads(re.search(r'<script type="application/json" id="rows">(.*?)</script>', index).group(1))
    by_popularity = {r["popularity"] for r in rows}
    assert by_popularity == {"well-known", "rare", "unknown"}
    assert '"lesser-known": "Lesser known"' not in index  # only levels that occur are offered


@pytest.mark.parametrize(
    "votes, expected",
    [(None, "unknown"), (0, "rare"), (9_999, "rare"), (10_000, "lesser-known"), (100_000, "well-known")],
)
def test_popularity_thresholds(votes, expected):
    item = site.Item(
        id=0, screening=None, cinema=None, start=NOW, title="x", labels=[], genres=[], imdb_votes=votes
    )
    assert item.popularity == expected
