"""Command line: `reflick scrape`, `enrich`, `build`, `prune` and `list`."""

import argparse
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from reflick import db, enrich, site
from reflick.adapters import ADAPTERS
from reflick.adapters.base import Fetcher
from reflick.omdb import OmdbClient
from reflick.revival import is_revival

DEFAULT_DB = Path("data/reflick.sqlite")
DEFAULT_OUT = Path("site")
BERLIN = ZoneInfo("Europe/Berlin")


def load_dotenv(path: Path = Path(".env")) -> None:
    """Read KEY=value lines into the environment; real env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.strip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def scrape(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    fetcher = Fetcher()
    cache = db.Cache(conn)
    problems = 0
    for source in args.source or list(ADAPTERS):
        adapter = ADAPTERS[source]()
        run_id = db.start_run(conn, source)
        try:
            programme = adapter.fetch(fetcher, cache)
        except Exception as exc:  # one broken source must not stop the others
            db.finish_run(conn, run_id, "failed", repr(exc))
            print(f"{source}: FAILED: {exc!r}", file=sys.stderr)
            problems += 1
            continue
        for cinema in programme.cinemas:
            db.upsert_cinema(conn, cinema)
        screenings = programme.screenings
        db.save_screenings(conn, run_id, screenings)
        for warning in programme.warnings:
            print(f"{source}: WARNING: {warning}", file=sys.stderr)
            problems += 1
        if not screenings:
            # A scraper that suddenly finds nothing has most likely broken.
            db.finish_run(conn, run_id, "empty")
            print(f"{source}: WARNING: 0 screenings", file=sys.stderr)
            problems += 1
            continue
        db.finish_run(conn, run_id, "ok")
        # In a group, one cinema going quiet can mean it was renamed in the data.
        per_cinema = Counter(s.cinema_id for s in screenings)
        for cinema in programme.cinemas:
            if not per_cinema[cinema.id]:
                print(f"{source}: WARNING: 0 screenings at {cinema.name}", file=sys.stderr)
                problems += 1
        revivals = sum(is_revival(s) for s in screenings)
        where = f" at {len(per_cinema)} cinemas" if len(programme.cinemas) > 1 else ""
        print(f"{source}: {len(screenings)} screenings{where}, {revivals} revivals")
    # Rebuild even if a cinema failed: the site falls back to its last good run.
    if not args.no_build:
        enrich_films(args)
        build(args)
    return 1 if problems else 0


def enrich_films(args: argparse.Namespace) -> int:
    api_key = os.environ.get("OMDB_API_KEY")
    if not api_key:
        print("omdb: OMDB_API_KEY not set, skipping genre lookup", file=sys.stderr)
        return 1
    retry = getattr(args, "retry", False)  # only `enrich` has the flag
    result = enrich.enrich(db.connect(args.db), OmdbClient(api_key), retry_misses=retry)
    print(
        f"omdb: {result.matched} matched, {result.missed} not found, "
        f"{result.cached} cached ({result.requests} requests)"
    )
    if result.error:
        print(f"omdb: stopped early: {result.error}", file=sys.stderr)
        return 1
    return 0


def build(args: argparse.Namespace) -> int:
    count = site.build(db.connect(args.db), args.out)
    print(f"site: {count} screenings written to {args.out}/")
    for page, placeholders in site.unfilled_placeholders(args.out).items():
        # A reminder, not an error: fill these in before the site goes public.
        print(f"site: WARNING: {page} still has placeholders: {', '.join(placeholders)}",
              file=sys.stderr)
    return 0


def prune(args: argparse.Namespace) -> int:
    removed = db.prune_runs(db.connect(args.db), keep=timedelta(days=args.keep_days))
    print(f"prune: removed {removed} runs older than {args.keep_days} days")
    return 0


def list_screenings(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    now = datetime.now(BERLIN)
    until = now + timedelta(days=args.days)
    for s in db.latest_screenings(conn):
        if not now <= s.start < until:
            continue
        if not args.all and not is_revival(s):
            continue
        facts = ", ".join(str(f) for f in (s.country, s.year, s.director) if f)
        lang = f" ({s.language})" if s.language else ""
        line = f"{s.start:%a %d.%m. %H:%M}  {s.cinema_id:<30} {s.title}{lang}"
        print(f"{line}  [{facts}]" if facts else line)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reflick")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="site output folder")
    sub = parser.add_subparsers(required=True)

    p_scrape = sub.add_parser(
        "scrape", help="fetch programmes, look up genres, then rebuild the site"
    )
    p_scrape.add_argument(
        "--source", action="append", choices=sorted(ADAPTERS),
        help="only scrape this source (a cinema or group); repeatable",
    )
    p_scrape.add_argument(
        "--no-build", action="store_true", help="skip the genre lookup and site build"
    )
    p_scrape.set_defaults(func=scrape)

    p_enrich = sub.add_parser("enrich", help="look up genres on OMDb (needs OMDB_API_KEY)")
    p_enrich.add_argument(
        "--retry", action="store_true", help="look up films that weren't found before again"
    )
    p_enrich.set_defaults(func=enrich_films)

    p_build = sub.add_parser("build", help="render the static site from the database")
    p_build.set_defaults(func=build)

    p_prune = sub.add_parser("prune", help="delete old scrape runs to keep the database small")
    p_prune.add_argument("--keep-days", type=int, default=28)
    p_prune.set_defaults(func=prune)

    p_list = sub.add_parser("list", help="show upcoming revival screenings")
    p_list.add_argument("--days", type=int, default=7)
    p_list.add_argument("--all", action="store_true", help="include non-revivals")
    p_list.set_defaults(func=list_screenings)

    args = parser.parse_args(argv)
    load_dotenv()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
