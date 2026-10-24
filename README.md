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
.venv/bin/reflick scrape          # fetch all cinemas
.venv/bin/reflick list --days 14  # upcoming revivals (--all for everything)
```

Cinemas covered so far: Lichtblick-Kino.

## Open decisions

- [x] Tech stack: Python
- [ ] Final name and domain (`.de` is cheapest, about €5–10/year; `.berlin`
      fits but costs about €40–60/year)
- [ ] Hosting: static site plus a daily scheduled job (VPS cron or GitHub
      Actions)

## Docs

- [Roadmap](docs/roadmap.md): the steps from scope to launch
