"""`reflick scrape` end to end with fake adapters: exit codes, run statuses and
the fallback to a source's last good run decide whether GitHub sends an alert."""

from datetime import datetime, timedelta

import pytest

from reflick import cli, db
from reflick.adapters.base import Adapter, Programme
from reflick.models import BERLIN, Cinema, RawScreening

ODEON = Cinema("odeon", "Odeon", "Hauptstr. 116", "Schöneberg", "https://odeon.example/")
ROXY = Cinema("roxy", "Roxy", "Hauptstr. 1", "Schöneberg", "https://roxy.example/")


def screening(cinema: Cinema, title: str = "Casablanca") -> RawScreening:
    start = datetime.now(BERLIN).replace(microsecond=0) + timedelta(days=2)
    return RawScreening(cinema_id=cinema.id, title=title, start=start, source_url=cinema.website, year=1942)


def adapter(source: str, result: Programme | Exception) -> type[Adapter]:
    class Fake(Adapter):
        id = source

        def fetch(self, fetcher, cache=None) -> Programme:
            if isinstance(result, Exception):
                raise result
            return result

    return Fake


@pytest.fixture
def run(tmp_path, monkeypatch):
    """Runs `reflick scrape --no-build` with the given adapters; returns the exit code and DB."""
    monkeypatch.chdir(tmp_path)  # no .env from the project
    monkeypatch.setattr(cli, "Fetcher", lambda: None)
    path = tmp_path / "test.sqlite"

    def scrape(*adapters: type[Adapter], build: bool = False) -> tuple[int, object]:
        monkeypatch.setattr(cli, "ADAPTERS", {a.id: a for a in adapters})
        args = ["--db", str(path), "--out", str(tmp_path / "site"), "scrape"]
        code = cli.main(args if build else [*args, "--no-build"])
        return code, db.connect(path)

    return scrape


def statuses(conn) -> list[tuple[str, str]]:
    return [tuple(r) for r in conn.execute("SELECT source, status FROM runs ORDER BY id")]


def test_good_sources_exit_zero(run, capsys):
    code, conn = run(adapter("odeon", Programme([ODEON], [screening(ODEON)])))
    assert code == 0
    assert statuses(conn) == [("odeon", "ok")]
    assert "odeon: 1 screenings, 1 revivals" in capsys.readouterr().out


def test_a_failing_source_does_not_stop_the_others(run, capsys):
    code, conn = run(
        adapter("broken", RuntimeError("layout changed")),
        adapter("odeon", Programme([ODEON], [screening(ODEON)])),
    )
    assert code == 1
    assert statuses(conn) == [("broken", "failed"), ("odeon", "ok")]
    assert "broken: FAILED: RuntimeError('layout changed')" in capsys.readouterr().err


def test_an_empty_source_falls_back_to_its_last_good_run(run):
    run(adapter("odeon", Programme([ODEON], [screening(ODEON, "Casablanca")])))
    code, conn = run(adapter("odeon", Programme([ODEON], [])))
    assert code == 1
    assert statuses(conn) == [("odeon", "ok"), ("odeon", "empty")]
    assert [s.title for s in db.latest_screenings(conn)] == ["Casablanca"]


def test_adapter_warnings_fail_the_run_but_keep_the_data(run, capsys):
    code, conn = run(adapter("odeon", Programme([ODEON], [screening(ODEON)], ["film x: no data"])))
    assert code == 1
    assert statuses(conn) == [("odeon", "ok")]
    assert "odeon: WARNING: film x: no data" in capsys.readouterr().err


def test_a_quiet_cinema_in_a_group_is_reported(run, capsys):
    code, conn = run(adapter("group", Programme([ODEON, ROXY], [screening(ODEON)])))
    assert code == 1
    assert statuses(conn) == [("group", "ok")]
    assert "group: WARNING: 0 screenings at Roxy" in capsys.readouterr().err


def test_the_site_is_built_even_when_a_source_fails(run, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "enrich_films", lambda args: 0)  # no Wikidata/OMDb requests
    code, _ = run(
        adapter("broken", RuntimeError("down")),
        adapter("odeon", Programme([ODEON], [screening(ODEON)])),
        build=True,
    )
    assert code == 1
    assert "Casablanca" in (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
