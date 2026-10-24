from datetime import datetime, timedelta, timezone

import httpx
import pytest

from reflick import db, enrich
from reflick.adapters.lichtblick import BERLIN, CINEMA
from reflick.models import RawScreening
from reflick.omdb import (
    OmdbClient,
    OmdbError,
    director_matches,
    find_film,
    title_variants,
)

CASABLANCA = {
    "Response": "True", "Title": "Casablanca", "Year": "1943", "imdbID": "tt0034583",
    "Genre": "Drama, Romance, War", "Director": "Michael Curtiz",
}
MODERN_TIMES = {
    "Response": "True", "Title": "Modern Times", "Year": "1936", "imdbID": "tt0027977",
    "Genre": "Comedy, Drama, Romance", "Director": "Charles Chaplin",
}
NOT_FOUND = {"Response": "False", "Error": "Movie not found!"}


def fake_client(answer) -> OmdbClient:
    """OmdbClient whose HTTP calls are answered by answer(params) -> JSON dict."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        return httpx.Response(200, json=answer(params))

    client = OmdbClient("secret-key", delay_s=0, client=httpx.Client(transport=httpx.MockTransport(handler)))
    client.calls = calls
    return client


def by_title(table):
    return lambda p: table.get(p.get("t") or p.get("i") or p.get("s"), NOT_FOUND)


def test_us_release_year_one_off_is_accepted():
    client = fake_client(by_title({"Casablanca": CASABLANCA}))
    match = find_film(client, "Casablanca", 1942, "Michael Curtiz")
    assert match.imdb_id == "tt0034583"
    assert match.genres == ["Drama", "Romance", "War"]
    assert len(client.calls) == 1


def test_wrong_director_is_rejected():
    client = fake_client(by_title({"Casablanca": CASABLANCA}))
    assert find_film(client, "Casablanca", 1942, "Someone Else") is None


def test_year_too_far_off_is_rejected():
    client = fake_client(by_title({"Casablanca": CASABLANCA}))
    assert find_film(client, "Casablanca", 1990, None) is None


def test_event_title_falls_back_to_film_title():
    client = fake_client(by_title({"Modern Times": MODERN_TIMES}))
    match = find_film(client, "Modern Times LIVE mit Babylon Orchester Berlin", 1936, "Charlie Chaplin")
    assert match.title == "Modern Times"


def test_search_fallback_checks_candidate_details():
    former = {
        "Response": "True", "Title": "Former East/Former West", "Year": "1994",
        "imdbID": "tt13953780", "Genre": "Documentary", "Director": "Shelly Silver",
    }

    def answer(p):
        if p.get("s") == "Former East / Former West":
            return {"Response": "True", "Search": [{"imdbID": "tt13953780"}]}
        if p.get("i") == "tt13953780":
            return former
        return NOT_FOUND

    match = find_film(fake_client(answer), "Former East / Former West", 1994, "Shelly Silver")
    assert match.genres == ["Documentary"]


def test_api_errors_do_not_leak_the_key():
    client = fake_client(lambda p: {"Response": "False", "Error": "Request limit reached!"})
    with pytest.raises(OmdbError) as exc:
        client.query(t="Casablanca")
    assert "limit" in str(exc.value)

    def broken(request):
        return httpx.Response(500)

    client = OmdbClient("secret-key", client=httpx.Client(transport=httpx.MockTransport(broken)))
    with pytest.raises(OmdbError) as exc:
        client.query(t="Casablanca")
    assert "secret-key" not in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__


@pytest.mark.parametrize(
    ("cinema", "omdb", "expected"),
    [
        ("Charlie Chaplin", "Charles Chaplin", True),
        ("Lew Kuleshov", "Lev Kuleshov", True),
        ("Moritz Enders und Gunther Merz", "Gunther Merz, Moritz Enders", True),
        ("Michael Curtiz", "Stanley Kubrick", False),
        (None, "Stanley Kubrick", True),
        ("Stanley Kubrick", "N/A", True),
    ],
)
def test_director_matches(cinema, omdb, expected):
    assert director_matches(cinema, omdb) is expected


def test_title_variants():
    assert "The Gold Rush" in title_variants("Chaplin's The Gold Rush with LIVE Orchestra")
    assert "Nosferatu" in title_variants("Nosferatu Live mit Babylon Orchester Berlin")
    assert "The Rocky Horror Picture Show" in title_variants(
        "The Rocky Horror Picture Show: Live Shadow Cast"
    )
    assert "Woman Demon Human" in title_variants("Huang Shuqin: Woman Demon Human")
    assert "The Exorcist" in title_variants("The Exorcist: Director's Cut")
    assert "Former East/Former West" in title_variants("Former East / Former West")
    assert title_variants("Casablanca") == ["Casablanca"]


def seeded(tmp_path, titles):
    conn = db.connect(tmp_path / "test.sqlite")
    db.upsert_cinema(conn, CINEMA)
    run = db.start_run(conn, CINEMA.id)
    db.save_screenings(conn, run, [
        RawScreening(
            cinema_id=CINEMA.id, title=title, year=year, director=None,
            start=datetime(2026, 11, 20, 20, 0, tzinfo=BERLIN), source_url="https://x/",
        )
        for title, year in titles
    ])
    db.finish_run(conn, run, "ok")
    return conn


def test_enrich_caches_matches_and_misses(tmp_path):
    conn = seeded(tmp_path, [("Casablanca", 1942), ("Unknown Film", 1960), ("New Film", 2026)])
    now = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
    client = fake_client(by_title({"Casablanca": CASABLANCA}))

    result = enrich.enrich(conn, client, now)
    assert (result.matched, result.missed) == (1, 1)  # New Film is no revival: not looked up
    assert db.film_info(conn) == {
        ("casablanca", 1942): db.FilmInfo("Casablanca", ["Drama", "Romance", "War"])
    }

    # Second run: both are cached, no requests.
    again = enrich.enrich(conn, fake_client(by_title({})), now)
    assert (again.cached, again.requests) == (2, 0)

    # A week later the miss is retried, the match isn't.
    later = enrich.enrich(conn, fake_client(by_title({})), now + timedelta(days=8))
    assert (later.cached, later.missed) == (1, 1)


def test_enrich_stops_on_api_error(tmp_path):
    conn = seeded(tmp_path, [("Casablanca", 1942)])
    client = fake_client(lambda p: {"Response": "False", "Error": "Invalid API key!"})
    result = enrich.enrich(conn, client, datetime(2026, 10, 24, tzinfo=timezone.utc))
    assert result.error == "OMDb: Invalid API key!"
    assert db.film_matches(conn) == {}
