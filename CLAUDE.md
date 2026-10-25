# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

reflick collects revival screenings (classics, restorations, re-releases) from Berlin cinema programmes and publishes them as a static site. README.md covers the product and setup in detail; docs/roadmap.md tracks what is done, partly done and open. Update its status markers when finishing a roadmap item.

## Commands

Python 3.12+, virtualenv in `.venv`, no linter configured.

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                                   # all tests (offline, use HTML fixtures)
.venv/bin/pytest tests/test_yorck.py -k film_page  # one file / one test
.venv/bin/reflick scrape [--source yorck] [--no-build]  # fetch, enrich via OMDb, build site
.venv/bin/reflick enrich [--retry]                 # OMDb genre lookup only
.venv/bin/reflick build                            # rebuild site/ from the DB only
.venv/bin/reflick list --days 14 [--all]           # upcoming revivals in the terminal
.venv/bin/reflick prune --keep-days 28
.venv/bin/python -m http.server 8765 --directory site   # preview (also in .claude/launch.json)
```

Global flags `--db` (default `data/reflick.sqlite`) and `--out` (default `site/`) go before the subcommand. `OMDB_API_KEY` is read from `.env` (gitignored); without it everything works except genres.

## Architecture

Pipeline: **adapters → SQLite snapshots → enrichment → static site**.

- **Adapters** (`src/reflick/adapters/`): one per *source*, which is either a single cinema (Babylon, Lichtblick) or a group publishing one programme for many cinemas (Yorck, 14 cinemas). Each subclasses `Adapter` (`base.py`), sets `id`, and implements `fetch(fetcher, cache) -> Programme` (cinemas + `RawScreening`s + warnings). Register new adapters in `adapters/__init__.py` `ADAPTERS`. Adapters split pure parse functions (`parse_programme`, `parse_film_page`, `parse_listing`, ...) from fetching, so tests call the parsers on fixtures in `tests/fixtures/<source>/` (real pages, trimmed to a few KB) and pass a `FakeFetcher` mapping URLs to fixture files.
- **Shared adapter helpers** (`base.py`), to reuse rather than re-implement: `clean` (whitespace), `date_without_year` (programmes print "24.10." without a year), `language_code` (unifies "Ohne Dialog"/"oD") and `fetch_pages` (paged listings sorted by date, stopping at a date limit; Arsenal and Zeughauskino are both TYPO3 Solr listings paged with `?tx_solr[page]=N`). When a listing lacks credits for some entries, read only those entries' detail pages and keep them (Yorck, Babylon, Zeughauskino) rather than fetching every detail page.
- **Fetcher** (`base.py`): all HTTP goes through it. It obeys robots.txt and waits 1s between requests. Adapters get a `Cache` (`db.Cache`): `film`/`save_film` keep a film's credits for good in the `films` table, by the source's own key (Yorck slug, Babylon page URL), so a returning film costs no request; `get`/`set` (`page_cache`, with a max age) are for anything else, e.g. Zeughauskino's per-screening pages.
- **Raw vs. cleaned data**: `RawScreening` (`models.py`) is stored exactly as the cinema publishes it in `raw_screenings`, one snapshot per scrape run (`runs` table, status `ok`/`empty`/`failed`). Title clean-up (`titles.py`: language suffixes, cinema add-ons turned into badges), language versions unified to OV/OmeU/OmdU/DF/oD (`languages.py`, add outliers to `OUTLIERS` there), and OMDb data are applied only at build time, so raw data can be reprocessed when matching improves. Don't push cleaning into adapters beyond what the cinema's format requires.
- **Last good run**: `db.latest_screenings` reads each source's most recent `ok` run, so a broken or empty source falls back to its previous data. `scrape` exits non-zero on any failure, empty source, adapter warning, or a group cinema with 0 screenings; the GitHub workflow still publishes and then fails the run to send an email.
- **Revival rule** (`revival.py`): year (Wikidata's release year when matched, `site.film_year`) at least 5 years ago, or a re-release keyword in series/tags/title. Only revivals appear on the site and in `list` (unless `--all`).
- **Enrichment** (`enrich.py`, `wikidata.py`, `omdb.py`), in two steps, both cached keyed by `(db.title_key(title), year)` with misses retried after a week:
  1. Wikidata (`film_titles`): German title, original title, IMDb id and first release year (used by the revival rule instead of the cinema's year), via full-text search with year ±1 and director check, or by IMDb id when OMDb already knows the film. Uses the Wikidata Action API directly, not the `Fetcher`: robots.txt disallows `/w/`, but Wikimedia's robot policy permits API use with one request at a time (~1/s) and a contact User-Agent. Don't add other robots.txt exceptions, and don't use the SPARQL endpoint.
  2. OMDb (`film_matches`): genres. By Wikidata's IMDb id when there is one, else by title variants, year ±1 and director.
  `db.film_info` merges both for the site: heading is the German title, original title shown underneath when it differs.
- **Site** (`site.py`, Jinja2 templates in `src/reflick/templates/`): writes `index.html` (single page grouped by day; screenings after midnight belong to the evening before), `reflick.ics`, `impressum.html`, `datenschutz.html`. Pico CSS and Alpine.js are vendored in `src/reflick/static/` (no CDN, no JS build step). Every screening is rendered as plain HTML and Alpine only hides non-matching rows, so the page must keep working without JavaScript. All links must stay relative (served under a GitHub Pages sub-path).
- **Schema changes**: tables are created with `CREATE TABLE IF NOT EXISTS` in `db.py`; new columns on existing tables go in `_migrate`.

## Conventions

- Times are timezone-aware `Europe/Berlin` (`models.BERLIN`, re-exported by `base`). For today's date use `models.berlin_today()`, not `date.today()` (CI runs in UTC). Code that stores timestamps takes an optional `now`, so tests pass a fixed clock instead of depending on the day they run.
- The site lists facts only (title, time, venue, link to the cinema's page). Don't copy cinema descriptions, images or trailers.
- Legal pages contain `[[ ... ]]` placeholders; `reflick build` warns while any remain.
- Commit messages: short imperative sentence, no prefix (e.g. "Add a date strip for picking days").
- Publishing: `.github/workflows/publish.yml` runs tests, scrapes daily at 03:33 Berlin time, keeps the DB in the Actions cache, and deploys `site/` to GitHub Pages.
