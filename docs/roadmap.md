# Roadmap

Ordered so the risky parts surface early.

## 1. Define scope

- [ ] Fix the revival rule (see README)
- [ ] Choose the first 5–8 cinemas

## 2. Survey data sources and legal side ← start here

For each cinema, record how its programme is published. This decides how hard
each scraper will be.

| Cinema | Programme URL | Format (JSON-LD / API / iCal / PDF / HTML) | robots.txt / terms OK? | Notes |
| --- | --- | --- | --- | --- |
| Arsenal | | | | |
| Zeughauskino | | | | |
| Babylon Mitte | | | | |
| Lichtblick-Kino | | | | Marks restorations as "Wiederaufführung in 4K" |
| Yorck group | | | | 14 cinemas, one shared programme |

- [ ] Read each site's terms and robots.txt
- [ ] Ask cinemas directly for a feed (small repertory cinemas often welcome
      the exposure)
- [ ] Plan the Impressum and the DSGVO privacy policy, which a public German
      site needs

If most cinemas offer structured data or clean HTML, the project is
straightforward. If most use PDFs, ingestion will take most of the effort.

## 3. Data model

- **Cinema**: name, address, neighbourhood, website
- **Film**: title, original title, year, director, external IDs (TMDB/Wikidata)
- **Screening**: film, cinema, start time, language/subtitles, format, ticket
  link, source URL
- **Series** (optional): e.g. a retrospective or classics series

Keep raw scraped data separate from cleaned data, so it can be reprocessed when
matching improves.

## 4. Ingestion pipeline

- One small adapter per cinema, all emitting the same screening format
- Daily scheduled run, storing a snapshot of each run
- Alert when a cinema suddenly returns zero screenings

## 5. Film matching and enrichment

- Match titles to TMDB or Wikidata for year, director and poster (check API
  terms and attribution)
- Clean titles: German vs. original titles, suffixes like "(OmU)" or
  "(35mm)", series prefixes
- Manual review queue for uncertain matches
- Apply the revival rule using the matched year plus any cinema tag

## 6. Storage and backend

- SQLite or Postgres
- Prefer generating the site statically after each ingestion run over running
  an API

## 7. Frontend

- "This week" list, day/calendar view
- Filters: cinema, neighbourhood, language/subtitles, format
- Film page with all upcoming screenings of one title
- iCal feed
- Mobile-first

## 8. Hosting and operations

- Static hosting plus a scheduled job (small VPS cron or GitHub Actions)
- Register the domain once the name is final

## 9. MVP launch

- A handful of cinemas, a simple list that is actually correct
- Tell the cinemas and local film communities; consider a weekly newsletter

## 10. Later

- Email or RSS alerts for a director or film
- A way for cinemas to submit their own programme
- Other cities
