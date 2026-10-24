# reflick

One place for all revival screenings in Berlin cinemas: classics, restorations,
re-releases and repertory series, collected from cinema programmes and shown
on a single website.

## Why

As far as we know, no site lists only Berlin's re-screenings. Right now you
have to check monthly guides (e.g. The Berliner's film events column), each
repertory cinema's own programme, or general listings such as kino.de, which
mix revivals in with new releases.

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
.venv/bin/reflick scrape          # fetch all sources, look up titles and genres, rebuild the site
.venv/bin/reflick scrape --source yorck  # just one source
.venv/bin/reflick enrich          # only look up titles and genres (--retry: re-check films not found)
.venv/bin/reflick build           # rebuild the site from the database only
.venv/bin/reflick list --days 14  # upcoming revivals in the terminal (--all for everything)
```

Cinemas covered so far: Arsenal, Babylon Mitte, Hackesche Höfe Kino,
Lichtblick-Kino, Zeughauskino, and the 14 Yorck cinemas (Babylon Kreuzberg,
Blauer Stern, Capitol Dahlem, Cinema Paris, Delphi Filmpalast, delphi LUX,
Filmtheater am Friedrichshain, Kant Kino, Kino International, Neues Off,
Odeon, Passage, Rollberg, Yorck).

Yorck's film pages (year, director, original title) are only read for
films that may be revivals, and cached for 30 days in the `page_cache`
table, so a daily run makes about ten requests once the cache is warm.

### Titles (Wikidata)

Every listed revival gets its German title and its original title from
[Wikidata](https://www.wikidata.org/), with no key needed. The site shows the
German title, with the original underneath when it differs ("Uhrwerk Orange"
/ "A Clockwork Orange"). A film is found by full-text search over all its
titles, so German, original and English titles all work; a match must share a
release year (±1) and, when the cinema names one, the director. Films OMDb
already knows are looked up by their IMDb id. Results are cached in the
`film_titles` table; films that weren't found are retried after a week.

Wikidata's robots.txt disallows its API (`/w/`) for crawlers, but
Wikimedia's [robot policy](https://wikitech.wikimedia.org/wiki/Robot_policy)
has explicit rules for API use, which reflick follows: one request at a
time, about one a second, and a User-Agent naming this repository. This is
the only place that doesn't go through the robots.txt check; the SPARQL
query service, which robots.txt also disallows, isn't used. The first run
looks up every listed film (about two requests each), later runs only new
ones.

### Genres (OMDb)

Genres come from [OMDb](https://www.omdbapi.com/), which needs a free API
key (1,000 requests a day). Put it in a `.env` file in the project folder,
which is gitignored:

```
OMDB_API_KEY=your-key
```

Without a key, scraping and the site still work, just without genres.

When Wikidata found the film's IMDb id, OMDb is asked for exactly that film.
Otherwise it's matched by title (the cinema's, or the original from
Wikidata), accepting a year off by one (OMDb uses the US release year) and
checking the director when the cinema names one. Results are cached in the
`film_matches` table, so each film costs requests only once; films that
weren't found are retried after a week, or right away once Wikidata has
found their IMDb id. The site credits OMDb in the footer, as its CC BY-NC
4.0 licence requires, and Wikidata (CC0) alongside.

### Website

`reflick build` (also run at the end of every `scrape`) writes a static site
to `site/`:

- `index.html`: a single page with all upcoming revivals across cinemas by
  day, with search, multi-select filters (cinema, district, language,
  genre) and a date strip with one chip per day. Each row's Details button
  opens the film's page on the cinema's own website. Late shows after midnight are
  listed under the evening before (e.g. 24:00), as cinemas do.
- Titles are shown without the cinemas' add-ons: "Modern Times LIVE mit
  Babylon Orchester Berlin" becomes "Modern Times" with a "Live mit Babylon
  Orchester Berlin" badge (see `src/reflick/titles.py`). When OMDb matched
  the film and its title differs in substance, OMDb's title is shown
  ("Chaplin's The Gold Rush" → "The Gold Rush"); the database keeps the
  cinema's original title.
- `reflick.ics`: a calendar feed to subscribe to.
- `impressum.html` and `datenschutz.html`: legal notice and privacy policy
  (German), required for a public site in Germany.

Templates live in `src/reflick/templates/` (Jinja2). Styling comes from
[Pico CSS](https://picocss.com/) and the filters use
[Alpine.js](https://alpinejs.dev/). Both are stored in `src/reflick/static/`
and served with the site, so visitors' browsers contact no third party and
there is no JavaScript build step (versions and licences in
`src/reflick/static/LICENSES.md`). Every screening is plain HTML; Alpine only
hides rows that don't match, so the page works without JavaScript too.

To preview locally:

```bash
python3 -m http.server 8000 --directory site
```

Then open http://localhost:8000. The folder can be deployed as-is to any
static host.

## Publishing (GitHub Pages)

`.github/workflows/publish.yml` scrapes once a day (04:00 UTC), looks up
genres, rebuilds the site and publishes it on GitHub Pages. It also runs on
pushes to `main` and from the "Run workflow" button in the Actions tab.

- The database is carried from run to run in the Actions cache, so OMDb
  matches and Yorck film credits are only fetched once. `reflick prune`
  keeps the last 28 days of scrape runs (plus each source's latest good run).
- If a cinema fails or suddenly returns nothing, the site is still published
  from its last good data, and the run is then marked as failed, so GitHub
  emails a warning.

One-time setup:

1. Fill in every `[[ ... ]]` placeholder in
   `src/reflick/templates/impressum.html` and `datenschutz.html`.
   `reflick build` warns while any are left. The texts are a starting point,
   not legal advice.
2. Create a **public** GitHub repository (Pages on private repositories
   needs a paid plan) and push `main` to it.
3. Settings → Pages → Build and deployment → Source: **GitHub Actions**.
4. Settings → Secrets and variables → Actions → New repository secret:
   `OMDB_API_KEY`. Without it the site is built without genres.
5. Actions → "Scrape and publish" → **Run workflow** for the first run. The
   site then lives at `https://<user>.github.io/<repository>/`; all links are
   relative, so that sub-path works.

For a custom domain, add a `CNAME` file containing the domain to the site
output, point the domain's DNS at GitHub Pages, and enable "Enforce HTTPS"
in the Pages settings.