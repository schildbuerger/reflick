# reflick

One place for all revival screenings in Berlin cinemas: classics, restorations,
re-releases and repertory series, collected from cinema programmes and shown
on a single website.

## Why

As far as we know, no site lists only Berlin's re-screenings. Right now you
have to check monthly guides (e.g. The Berliner's film events column), each
repertory cinema's own programme, or general listings such as kino.de, which
mix revivals in with new releases.

## Name

"Reflick" combines "re" with the old slang "flicks" for films. It's a working
title. The domain is not registered yet, and availability is unconfirmed
(check `reflick.de` at denic.de). Other names that showed no existing web
presence: rekino, nachbild, wiederkino.

## What counts as a revival

Starting rule: a film's original release year is at least 5 years ago, **or**
the cinema labels it as a re-release. Typical labels in German programmes:
"Wiederaufführung", "Filmklassiker", "Reprise", "restauriert",
"4K-Restaurierung", "Best of Cinema".

## MVP scope

- Berlin only, 5–8 cinemas with lots of repertory programming, for example
  Arsenal, Zeughauskino, Babylon Mitte, Lichtblick-Kino, the Yorck cinemas
  (Kino International, Delphi Filmpalast) and a few Kiez cinemas.
- A correct "this week" list with filters for cinema, language/subtitles and
  format (35mm, 4K restoration).
- Every screening links to the cinema's own ticket page. We list facts (title,
  time, venue) and don't copy descriptions, images or trailers.

## Development

Python 3.12+. One adapter per source lives in `src/reflick/adapters/`. A
source is a single cinema (Babylon Mitte, Lichtblick-Kino) or a group that
publishes one programme for several cinemas (Yorck, 14 cinemas). Each scrape
run of a source is stored as a snapshot in a local SQLite database
(`data/reflick.sqlite`). A scrape warns when a source, or a single cinema in
a group, suddenly has no screenings, which usually means its site changed.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/reflick scrape          # fetch all sources, look up genres, rebuild the site
.venv/bin/reflick scrape --source yorck  # just one source
.venv/bin/reflick enrich          # only look up genres (--retry: re-check films not found)
.venv/bin/reflick build           # rebuild the site from the database only
.venv/bin/reflick list --days 14  # upcoming revivals in the terminal (--all for everything)
```

Cinemas covered so far: Babylon Mitte, Lichtblick-Kino, and the 14 Yorck
cinemas (Babylon Kreuzberg, Blauer Stern, Capitol Dahlem, Cinema Paris,
Delphi Filmpalast, delphi LUX, Filmtheater am Friedrichshain, Kant Kino,
Kino International, Neues Off, Odeon, Passage, Rollberg, Yorck).

Yorck's film pages (year, director, original title) are only read for
films that may be revivals, and cached for 30 days in the `page_cache`
table, so a daily run makes about ten requests once the cache is warm.

### Genres (OMDb)

Genres come from [OMDb](https://www.omdbapi.com/), which needs a free API
key (1,000 requests a day). Put it in a `.env` file in the project folder,
which is gitignored:

```
OMDB_API_KEY=your-key
```

Without a key, scraping and the site still work, just without genres.

Each listed revival is matched by title, accepting a year off by one (OMDb
uses the US release year) and checking the director when the cinema names
one. Results are cached in the `film_matches` table, so each film costs
requests only once; films that weren't found are retried after a week.
OMDb only knows English and original titles, so films listed under a German
title (e.g. "Aguirre, der Zorn Gottes") usually get no genre. The site
credits OMDb in the footer, as its CC BY-NC 4.0 licence requires.

### Website

`reflick build` (also run at the end of every `scrape`) writes a static site
to `site/`:

- `index.html`: a single page with all upcoming revivals across cinemas by
  day, with search, cinema and language filters. Each title links to the
  film's page on the cinema's own website. Late shows after midnight are
  listed under the evening before (e.g. 24:00), as cinemas do.
- Titles are shown without the cinemas' add-ons: "Modern Times LIVE mit
  Babylon Orchester Berlin" becomes "Modern Times" with a "Live mit Babylon
  Orchester Berlin" badge (see `src/reflick/titles.py`). When OMDb matched
  the film and its title differs in substance, OMDb's title is shown
  ("Chaplin's The Gold Rush" → "The Gold Rush"); the database keeps the
  cinema's original title.
- `reflick.ics`: a calendar feed to subscribe to.

Templates live in `src/reflick/templates/` (Jinja2). Styling comes from
[Pico CSS](https://picocss.com/) and the filters use
[Alpine.js](https://alpinejs.dev/), both loaded from a CDN, so there is no
JavaScript build step. Every screening is plain HTML; Alpine only hides rows
that don't match, so the page works without JavaScript too.

To preview locally:

```bash
python3 -m http.server 8000 --directory site
```

Then open http://localhost:8000. The folder can be deployed as-is to any
static host.

## Open decisions

- [x] Tech stack: Python
- [ ] Final name and domain (`.de` is cheapest, about €5–10/year; `.berlin`
      fits but costs about €40–60/year)
- [ ] Hosting: static site plus a daily scheduled job (VPS cron or GitHub
      Actions)

## Docs

- [Roadmap](docs/roadmap.md): the steps from scope to launch
