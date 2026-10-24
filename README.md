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

Python 3.12+. One adapter per cinema lives in `src/reflick/adapters/`; each
scrape run is stored as a snapshot in a local SQLite database
(`data/reflick.sqlite`).

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/reflick scrape          # fetch all cinemas, then rebuild the site
.venv/bin/reflick build           # rebuild the site from the database only
.venv/bin/reflick list --days 14  # upcoming revivals in the terminal (--all for everything)
```

Cinemas covered so far: Lichtblick-Kino.

### Website

`reflick build` (also run at the end of every `scrape`) writes a static site
to `site/`:

- `index.html`: a single page with all upcoming revivals across cinemas by
  day, with search, cinema and language filters. Each title links to the
  film's page on the cinema's own website. Late shows after midnight are
  listed under the evening before (e.g. 24:00), as cinemas do.
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
