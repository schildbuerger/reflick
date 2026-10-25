from datetime import date, datetime
from pathlib import Path

from reflick.adapters.brotfabrik import BERLIN, BrotfabrikAdapter, credits_line, parse_credits, parse_page
from reflick.languages import language_version
from reflick.revival import is_revival

FIXTURES = Path(__file__).parent / "fixtures" / "brotfabrik"
TODAY = date(2026, 10, 25)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def by_title(screenings, title):
    [s] = [s for s in screenings if s.title == title]
    return s


def test_event_with_credits():
    screenings, last = parse_page(fixture("events-1.json"))
    assert not last
    s = by_title(screenings, "Kuhle Wampe oder Wem gehört die Welt?")
    assert s.start == datetime(2026, 10, 27, 19, 0, tzinfo=BERLIN)
    assert (s.country, s.year, s.runtime_min, s.director) == ("D", 1932, 71, "Slatan Dudow")
    assert s.source_url == "https://brotfabrik-berlin.de/veranstaltung/kuhle-wampe-oder-wem-gehoert-die-welt/"
    assert s.ticket_url.startswith("https://")
    assert is_revival(s, TODAY)


def test_runtime_and_genre_in_one_segment():
    s = by_title(parse_page(fixture("events-1.json"))[0], "Don Camillos Rückkehr")
    assert (s.country, s.year, s.runtime_min, s.director) == ("F/IT", 1953, 115, "Julien Duvivier")


def test_original_title_before_country_and_several_directors():
    s = by_title(parse_page(fixture("events-1.json"))[0], "Marta Dzido: Die Frauen der Solidarność")
    assert s.original_title == "Solidarność Według Kobiet"
    assert (s.country, s.year, s.director, s.language) == ("Polen", 2014, "Marta Dzido, Piotr Śliwowski", "OmU")


def test_silent_film_notes_are_its_language_version():
    s = by_title(parse_page(fixture("events-1.json"))[0], "Kohlhiesels Töchter")
    assert s.director == "Ernst Lubitsch"
    assert s.language == "deutsche Zwischentitel, englische Untertitel"
    assert language_version(s.language) == "OmeU"


def test_event_without_credits_is_kept():
    s = by_title(parse_page(fixture("events-1.json"))[0], "The Killer")
    assert (s.year, s.director) == (None, None)


def test_last_page():
    screenings, last = parse_page(fixture("events-3.json"))
    assert last
    assert by_title(screenings, "La Haine").language == "OmU"


def test_parse_credits_ignores_unknown_segments():
    assert parse_credits("UK 2010 | 87 min | Dokumentarfilm | R: Banksy | OmU") == {
        "country": "UK", "year": 2010, "runtime_min": 87, "director": "Banksy", "language": "OmU",
    }


def test_credits_broken_over_lines_and_year_spans():
    line = credits_line("<p>30.10., 19 Uhr</p><p>D 1925/26 | Stummfilm | R: G.W. Pabst |<br>\n"
                        "deutsche Zwischentitel | englische Untertitel</p>")
    assert parse_credits(line) == {
        "country": "D", "year": 1925, "director": "G.W. Pabst",
        "language": "deutsche Zwischentitel, englische Untertitel",
    }
    line = credits_line("<p>UK 2026 | 80 min | Dokumentarfilm | R:<br>\nYuval Abraham &amp; Rachel Szor | OmU</p>")
    assert parse_credits(line)["director"] == "Yuval Abraham & Rachel Szor"


def test_adapter_reads_every_page():
    class FakeFetcher:
        requested: list[str] = []

        def get(self, url):
            self.requested.append(url)
            assert "categories=kino" in url
            return fixture("events-1.json" if url.endswith("page=1") else "events-3.json")

    fetcher = FakeFetcher()
    programme = BrotfabrikAdapter().fetch(fetcher)
    assert [c.id for c in programme.cinemas] == ["brotfabrik"]
    assert [u[-6:] for u in fetcher.requested] == ["page=1", "page=2"]
    assert len(programme.screenings) == 8
