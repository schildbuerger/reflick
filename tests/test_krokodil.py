from datetime import date, datetime
from pathlib import Path

from reflick.adapters.krokodil import (
    BASE_URL,
    BERLIN,
    PROGRAMME_URL,
    KrokodilAdapter,
    parse_credits,
    parse_film_page,
    parse_programme,
)
from reflick.languages import language_version
from reflick.revival import is_revival

FIXTURES = Path(__file__).parent / "fixtures" / "krokodil"
TODAY = date(2026, 10, 25)
HEIMSUCHUNG = f"{BASE_URL}/film/heimsuchung-eine-jahrhundertgeschichte/"
PIGEONS = f"{BASE_URL}/film/if-pigeons-turned-to-gold/"
DEFA = (
    f"{BASE_URL}/film/defa-stiftung-praesentiert-nie-wieder-leb-ich-zu-auf-eine-wende-"
    "defa-dokumentarfilme-von-thomas-kuschel-aus-der-wendezeit/"
)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_programme_links_each_film_once():
    assert parse_programme(fixture("programm.html")) == [HEIMSUCHUNG, PIGEONS, DEFA]


def test_film_page_dates_and_credits():
    screenings = parse_film_page(fixture("heimsuchung.html"), HEIMSUCHUNG)
    assert len(screenings) == 11
    s = screenings[0]
    assert s.title == "Heimsuchung – Eine Jahrhundertgeschichte"  # without soft hyphens
    # The page says 19:00+00:00 for a 19:00 screening in Berlin.
    assert s.start == datetime(2026, 10, 25, 19, 0, tzinfo=BERLIN)
    assert (s.country, s.year, s.runtime_min, s.director) == ("Deutschland", 2026, 122, "Volker Schlöndorff")
    assert s.language == "deutsche Originalfassung"
    assert language_version(s.language) is None
    assert s.ticket_url.startswith("https://www.kinoheld.de/")
    assert s.source_url == HEIMSUCHUNG
    assert not is_revival(s, TODAY)


def test_subtitled_film():
    [s, *_] = parse_film_page(fixture("if-pigeons.html"), PIGEONS)
    assert s.language == "Tschechisch | Englisch mit deutschen UT"
    assert language_version(s.language) == "OmdU"
    assert s.director == "Pepa Lubojacki"  # after a line about an award


def test_programme_of_several_films_takes_the_first():
    [s] = parse_film_page(fixture("defa.html"), DEFA)
    assert (s.year, s.director) == (1989, "Thomas Kuschel")
    assert is_revival(s, TODAY)


def test_parse_credits_variants():
    assert parse_credits(["UdSSR 1966 / 67, 95 min., OmeU", "R: Andrei Tarkowski"]) == {
        "country": "UdSSR", "year": 1966, "runtime_min": 95, "language": "OmeU", "director": "Andrei Tarkowski",
    }
    assert parse_credits(["Eine Lesung mit Gespräch"]) == {}


class FakeFetcher:
    pages = {
        PROGRAMME_URL: "programm.html", HEIMSUCHUNG: "heimsuchung.html", PIGEONS: "if-pigeons.html", DEFA: "defa.html",
    }

    def __init__(self):
        self.requested: list[str] = []

    def get(self, url: str) -> str:
        self.requested.append(url)
        return fixture(self.pages[url])


def test_adapter_reads_every_film_page():
    fetcher = FakeFetcher()
    programme = KrokodilAdapter().fetch(fetcher)
    assert fetcher.requested == [PROGRAMME_URL, HEIMSUCHUNG, PIGEONS, DEFA]
    assert len(programme.screenings) == 1 + 11 + 3
    assert programme.cinemas[0].lat is not None
