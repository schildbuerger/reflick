from datetime import timedelta
from pathlib import Path

import pytest

from reflick.adapters.yorck import (
    BASE_URL,
    YorckAdapter,
    next_data,
    parse_cinemas,
    parse_film_page,
    parse_listing,
)

FIXTURES = Path(__file__).parent / "fixtures" / "yorck"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


PAGES = {
    f"{BASE_URL}/kinos": "kinos.html",
    f"{BASE_URL}/filme": "filme.html",
    f"{BASE_URL}/specials/halloween-im-kant": "special-halloween-im-kant.html",
    f"{BASE_URL}/filme/angel-heart": "film-angel-heart.html",
    f"{BASE_URL}/filme/hereditary-das-vermachtnis": "film-hereditary-das-vermachtnis.html",
    f"{BASE_URL}/filme/the-rocky-horror-picture-show": "film-the-rocky-horror-picture-show.html",
    f"{BASE_URL}/filme/the-texas-chainsaw-massacre": "film-the-texas-chainsaw-massacre.html",
}


class FakeFetcher:
    def __init__(self, pages=PAGES):
        self.pages = pages
        self.requested: list[str] = []

    def get(self, url: str) -> str:
        self.requested.append(url)
        if url not in self.pages:
            raise AssertionError(f"unexpected request: {url}")
        return fixture(self.pages[url])


class MemoryCache:
    def __init__(self):
        self.data = {}
        self.films = {}

    def get(self, namespace, key, max_age):
        return self.data.get((namespace, key))

    def set(self, namespace, key, value):
        self.data[(namespace, key)] = value

    def film(self, source, key):
        return self.films.get((source, key))

    def save_film(self, source, key, credits):
        self.films[(source, key)] = credits


@pytest.fixture
def programme():
    return YorckAdapter().fetch(FakeFetcher(), MemoryCache())


def by_title(programme, title):
    return [s for s in programme.screenings if s.title == title]


def test_all_fourteen_cinemas_with_addresses():
    cinemas = parse_cinemas(next_data(fixture("kinos.html")))
    assert len(cinemas) == 14
    blauer_stern = cinemas["blauer stern"]  # the feed has "Blauer Stern " with a space
    assert blauer_stern.id == "yorck-blauer-stern"
    assert blauer_stern.name == "Blauer Stern"
    assert blauer_stern.address == "Hermann-Hesse-Straße 11, 13156 Berlin"
    assert blauer_stern.neighbourhood == "Pankow"
    assert cinemas["babylon kreuzberg"].id == "yorck-babylon-kreuzberg"


def test_programme_lists_every_cinema(programme):
    assert len(programme.cinemas) == 14
    assert programme.warnings == []


def test_classic_gets_credits_from_its_film_page(programme):
    [first, *_] = by_title(programme, "Angel Heart")
    assert (first.year, first.director, first.country) == (1987, "Alan Parker", "Great Britain, USA")
    assert first.source_url == f"{BASE_URL}/filme/angel-heart"
    assert first.cinema_id.startswith("yorck-")
    assert first.original_title is None  # same as the title


def test_series_from_a_special_that_shares_the_session(programme):
    # The fixture's "Kult im Kant" special lists one of Angel Heart's three sessions.
    in_series = [s for s in by_title(programme, "Angel Heart") if s.series]
    assert [s.series for s in in_series] == ["Kult im Kant"]
    assert "Klassiker" in in_series[0].tags


def test_new_film_is_not_looked_up(programme):
    [s, *_] = by_title(programme, "Vaterland")
    assert s.year == 2026  # from the German release date
    assert s.director is None


def test_series_only_sessions_come_from_the_special_page(programme):
    [s] = by_title(programme, "Hereditary – Das Vermächtnis")
    assert s.series == "Halloween im Kant"
    assert s.language == "OmU"
    assert s.original_title == "Hereditary"
    assert s.cinema_id == "yorck-kant-kino"


def test_sneak_previews_are_skipped(programme):
    assert not any("sneak" in s.title.casefold() for s in programme.screenings)


def test_readings_are_not_fetched():
    fetcher = FakeFetcher()
    YorckAdapter().fetch(fetcher, MemoryCache())
    assert not any("literatur" in url for url in fetcher.requested)


def test_film_pages_are_cached():
    cache = MemoryCache()
    YorckAdapter().fetch(FakeFetcher(), cache)
    second = FakeFetcher()
    YorckAdapter().fetch(second, cache)
    assert not any("/filme/" in url for url in second.requested)


def test_unknown_cinema_is_reported_not_dropped_silently():
    listing = fixture("filme.html").replace('"name": "Yorck"', '"name": "Yorck Neu"')
    assert listing != fixture("filme.html")

    class Renamed(FakeFetcher):
        def get(self, url):
            return listing if url == f"{BASE_URL}/filme" else super().get(url)

    programme = YorckAdapter().fetch(Renamed(), MemoryCache())
    assert "unknown cinema in programme: 'Yorck Neu'" in programme.warnings


def test_parse_listing_finds_specials_with_own_sessions():
    sessions, pending = parse_listing(next_data(fixture("filme.html")))
    assert pending == ["halloween-im-kant"]  # the reading is skipped
    assert all(s.start.tzinfo is not None for s in sessions.values())


def test_parse_film_page():
    assert parse_film_page(next_data(fixture("film-the-texas-chainsaw-massacre.html")))["year"] == 1974


BROKEN_FILM_PAGE = (
    '<script id="__NEXT_DATA__" type="application/json">{"props": {"pageProps": {"key": "x"}}}</script>'
)


def no_retry_delay() -> YorckAdapter:
    adapter = YorckAdapter()
    adapter.retry_delay_s = 0
    return adapter


def test_film_page_without_film_data_is_a_warning_and_not_cached():
    class Flaky(FakeFetcher):
        def get(self, url):
            if url == f"{BASE_URL}/filme/angel-heart":
                self.requested.append(url)
                return BROKEN_FILM_PAGE
            return super().get(url)

    cache = MemoryCache()
    fetcher = Flaky()
    programme = no_retry_delay().fetch(fetcher, cache)
    assert fetcher.requested.count(f"{BASE_URL}/filme/angel-heart") == 3
    assert any("film angel-heart" in w for w in programme.warnings)
    assert ("yorck", "angel-heart") not in cache.films
    [s, *_] = by_title(programme, "Angel Heart")
    assert s.year == 1987  # falls back to the German release year


def test_film_page_without_film_data_is_retried():
    class FlakyOnce(FakeFetcher):
        def get(self, url):
            if url == f"{BASE_URL}/filme/angel-heart" and url not in self.requested:
                self.requested.append(url)
                return BROKEN_FILM_PAGE
            return super().get(url)

    programme = no_retry_delay().fetch(FlakyOnce(), MemoryCache())
    assert programme.warnings == []
    [s, *_] = by_title(programme, "Angel Heart")
    assert s.director == "Alan Parker"
