import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from reflick import db, enrich, site
from reflick.adapters.lichtblick import BERLIN, CINEMA
from reflick.models import RawScreening
from reflick.omdb import OmdbClient
from reflick.wikidata import WikidataClient, WikidataError, find_film, search_text

# Real API responses, trimmed to the properties the client reads, keyed by
# their query parameters (recorded from www.wikidata.org on 2026-10-24).
RESPONSES = json.loads(
    (Path(__file__).parent / "fixtures" / "wikidata" / "responses.json").read_text(encoding="utf-8")
)
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def replay_client() -> WikidataClient:
    """A WikidataClient answering from RESPONSES; unknown requests fail the test."""

    def handler(request: httpx.Request) -> httpx.Response:
        params = {k: v for k, v in request.url.params.items() if k not in ("format", "formatversion")}
        key = json.dumps(params, sort_keys=True, ensure_ascii=False)
        assert key in RESPONSES, f"unexpected request: {key}"
        return httpx.Response(200, json=RESPONSES[key])

    return WikidataClient(delay_s=0, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_german_title_finds_film_with_original_title():
    film = find_film(replay_client(), "Das Appartement", 1960, "Billy Wilder")
    assert (film.qid, film.title_de, film.original_title) == ("Q270510", "Das Appartement", "The Apartment")
    assert film.imdb_id == "tt0053604"


def test_original_title_finds_german_title():
    film = find_film(replay_client(), "La règle du jeu", 1939, "Jean Renoir")
    assert (film.title_de, film.original_title) == ("Die Spielregel", "La Règle du jeu")


def test_known_imdb_id_is_looked_up_directly():
    client = replay_client()
    film = find_film(client, "Aguirre, der Zorn Gottes", 1972, "Werner Herzog", imdb_id="tt0068182")
    assert film.title_de == film.original_title == "Aguirre, der Zorn Gottes"
    assert client.requests == 2  # search by id, then the item


def test_wrong_year_is_no_match():
    # The cinema gives 2021; Spirited Away is from 2001 (re-released 2002, 2003, 2024).
    assert find_film(replay_client(), "Chihiros Reise ins Zauberland", 2021, "Hayao Miyazaki") is None


def test_wrong_director_is_no_match():
    assert find_film(replay_client(), "Das Appartement", 1960, "Fritz Lang") is None


def test_search_text_drops_addons_and_operators():
    assert search_text("Modern Times LIVE mit Babylon Orchester Berlin") == "Modern Times"
    assert search_text('"Filme statt Bomben" -Nacht') == "Filme statt Bomben Nacht"


def test_rate_limit_is_an_error():
    def handler(request):
        return httpx.Response(429, headers={"Retry-After": "60"})

    client = WikidataClient(delay_s=0, client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(WikidataError, match="HTTPStatusError"):
        client.search("x")


def seeded(tmp_path, films):
    conn = db.connect(tmp_path / "test.sqlite")
    db.upsert_cinema(conn, CINEMA)
    run = db.start_run(conn, CINEMA.id)
    db.save_screenings(conn, run, [
        RawScreening(
            cinema_id=CINEMA.id, title=title, year=year, director=director,
            start=datetime(2026, 11, 20, 20, 0, tzinfo=BERLIN), source_url="https://x/",
        )
        for title, year, director in films
    ])
    db.finish_run(conn, run, "ok")
    return conn


def test_enrich_titles_caches_matches_and_misses(tmp_path):
    conn = seeded(tmp_path, [
        ("Das Appartement", 1960, "Billy Wilder"),
        ("Chihiros Reise ins Zauberland", 2021, "Hayao Miyazaki"),
    ])
    result = enrich.enrich_titles(conn, replay_client(), NOW)
    assert (result.matched, result.missed) == (1, 1)
    info = db.film_info(conn)[("das appartement", 1960)]
    assert (info.title_de, info.original_title, info.imdb_id) == ("Das Appartement", "The Apartment", "tt0053604")
    assert info.genres == []  # OMDb hasn't been asked yet

    assert info.year == 1960  # the earliest of 1960 and 1961

    again = enrich.enrich_titles(conn, replay_client(), NOW)
    assert (again.cached, again.requests) == (2, 0)


def test_matches_from_before_release_years_get_them_once(tmp_path):
    conn = seeded(tmp_path, [("Aguirre, der Zorn Gottes", 1972, "Werner Herzog")])
    db.save_film_titles(conn, "Aguirre, der Zorn Gottes", 1972, "Q325662", "Aguirre", None, "tt0068182")
    client = replay_client()
    enrich.enrich_titles(conn, client, NOW)
    assert client.requests == 1  # the item by its id, no new search
    # OMDb says 1977, the US release; Wikidata's earliest date is the premiere.
    assert db.film_info(conn)[(db.title_key("Aguirre, der Zorn Gottes"), 1972)].year == 1972
    assert enrich.enrich_titles(conn, replay_client(), NOW).requests == 0


def test_omdb_uses_the_imdb_id_from_wikidata(tmp_path):
    conn = seeded(tmp_path, [("Das Appartement", 1960, "Billy Wilder")])
    # OMDb looked before Wikidata knew the film, and missed the German title.
    db.save_film_match(conn, "Das Appartement", 1960, None, None, [])
    enrich.enrich_titles(conn, replay_client(), NOW)

    calls = []

    def handler(request):
        calls.append(dict(request.url.params))
        return httpx.Response(200, json={
            "Response": "True", "Title": "The Apartment", "Year": "1960", "imdbID": "tt0053604",
            "Genre": "Comedy, Drama, Romance", "Director": "Billy Wilder",
        })

    omdb = OmdbClient("key", delay_s=0, client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = enrich.enrich(conn, omdb, NOW)  # the miss is less than a week old, but retried
    assert result.matched == 1
    assert [c["i"] for c in calls] == ["tt0053604"]
    assert db.film_info(conn)[("das appartement", 1960)].genres == ["Comedy", "Drama", "Romance"]

    # Matched now: no more requests.
    unused = OmdbClient("key", delay_s=0, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert enrich.enrich(conn, unused, NOW + timedelta(days=8)).requests == 0


def test_site_shows_german_and_original_title(tmp_path):
    conn = seeded(tmp_path, [("La règle du jeu", 1939, "Jean Renoir"), ("Das Appartement", 1960, None)])
    db.save_film_titles(conn, "La règle du jeu", 1939, "Q748599", "Die Spielregel", "La Règle du jeu", "tt0031885")
    db.save_film_titles(conn, "Das Appartement", 1960, "Q270510", "Das Appartement", "The Apartment", None)
    out = tmp_path / "site"
    site.build(conn, out, now=datetime(2026, 10, 24, 12, 0, tzinfo=BERLIN))
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "<h3>Die Spielregel</h3>" in index
    assert '<p class="original-title muted">La Règle du jeu</p>' in index
    assert '<p class="original-title muted">The Apartment</p>' in index
    rows = json.loads(re.search(r'<script type="application/json" id="rows">(.*?)</script>', index).group(1))
    assert any(r["text"].startswith("die spielregel la règle du jeu") for r in rows)  # both searchable
    assert 'href="https://letterboxd.com/imdb/tt0031885/"' in index  # Wikidata's IMDb id


def test_same_titles_are_shown_once(tmp_path):
    conn = seeded(tmp_path, [("Aguirre, der Zorn Gottes", 1972, None)])
    db.save_film_titles(
        conn, "Aguirre, der Zorn Gottes", 1972, "Q325662",
        "Aguirre, der Zorn Gottes", "Aguirre, der Zorn Gottes", "tt0068182",
    )
    out = tmp_path / "site"
    site.build(conn, out, now=datetime(2026, 10, 24, 12, 0, tzinfo=BERLIN))
    assert "original-title" not in (out / "index.html").read_text(encoding="utf-8").split("<main")[1]
