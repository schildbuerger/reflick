from datetime import date, datetime
from pathlib import Path

from reflick.adapters.ilkino import BERLIN, PROGRAMME_URL, IlKinoAdapter, parse_programme
from reflick.languages import language_version
from reflick.revival import is_revival

FIXTURES = Path(__file__).parent / "fixtures" / "ilkino"
TODAY = date(2026, 10, 25)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def screenings():
    return parse_programme(fixture("movie-program.html"))


def at(hour: int, minute: int):
    [s] = [s for s in screenings() if (s.start.hour, s.start.minute) == (hour, minute)]
    return s


def test_screening_with_movie_facts():
    s = at(15, 0)
    assert s.title == "NAZA"
    assert s.start == datetime(2026, 10, 25, 15, 0, tzinfo=BERLIN)
    assert (s.year, s.director, s.runtime_min) == (2026, "Yuval Abraham, Rachel Szor", 80)
    assert s.source_url == "https://ilkino.de/movies/naza"
    assert s.ticket_url.startswith("https://www.kinoheld.de/")
    assert not is_revival(s, TODAY)


def test_language_version_follows_the_subtitles():
    assert at(15, 0).language == "OmdU"  # German subtitles
    assert at(19, 50).language == "OmeU"  # the same film with English ones
    assert at(18, 0).language == "OmdeU"  # both, kept as written
    assert language_version("OmdeU") == "OmdeU"
    assert at(13, 30).language is None  # none: dubbed or original, unknown


def test_unknown_director_and_year():
    s = at(11, 0)  # a short-film evening
    assert s.director is None  # "(Unknown)" in the data
    sneak = next(s for s in screenings() if s.title == "SNEAK PREVIEW")
    assert sneak.year is None


class FakeFetcher:
    def __init__(self):
        self.requested: list[str] = []

    def get(self, url: str) -> str:
        self.requested.append(url)
        return fixture("movie-program.html")


def test_adapter_reads_one_page():
    fetcher = FakeFetcher()
    programme = IlKinoAdapter().fetch(fetcher)
    assert fetcher.requested == [PROGRAMME_URL]
    assert len(programme.screenings) == 6
    assert programme.cinemas[0].neighbourhood == "Neukölln"
