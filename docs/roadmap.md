# Roadmap

Ordered so the risky parts surface early. Status as of 2026-10-24:
`[x]` done, `[~]` partly done, `[ ]` open.

## 1. Define scope

- [x] Fix the revival rule: the film's year is at least 5 years ago, or the
      cinema labels it a re-release (see README)
- [x] Choose the first cinemas: Arsenal, Babylon Mitte, Hackesche Höfe Kino,
      Lichtblick-Kino, Zeughauskino and the 14 Yorck cinemas
- [ ] Decide whether a cinema's label alone should count for recent films
      (Yorck files e.g. *Bottoms* (2023) under "Klassiker")

## 2. Survey data sources and legal side

For each cinema, record how its programme is published. This decides how hard
each scraper will be.

| Cinema | Programme URL | Format (JSON-LD / API / iCal / PDF / HTML) | robots.txt / terms OK? | Notes |
| --- | --- | --- | --- | --- |
| Arsenal | arsenal-berlin.de/kalender/ (now in Wedding, Plantagenstraße 30) | JSON API behind the calendar (`/api/v1/search/calendar/`, TYPO3 Solr, 12 events a page) with credits, format, language, series and ticket link | robots.txt returns 404 (no rules) | **Adapter done.** Dates without year. Foyer events are installations and skipped. Tickets via kinotickets.express |
| Zeughauskino | dhm.de/zeughauskino/spielplan/ | HTML (TYPO3 Solr listing, 10 a page) with ISO start time, series, country/year, format, sometimes language | Allowed | **Adapter done.** Listing runs on into placeholder dates (2064) after the real programme, so paging stops 180 days ahead. Screenings with guests lack facts in the listing; their pages are read and cached. macOS curl rejects the certificate chain, Python/httpx doesn't. Tickets via cinetixx |
| Babylon Mitte | babylonberlin.eu/programm | HTML (Joomla), no JSON-LD; whole programme on one page, one `li.mix` per screening with full timestamp | Allowed | **Adapter done.** Credit line is cut off, so film pages are read when the year is missing. Also lists theatre and readings (skipped). Server omits its intermediate certificate: Python/httpx copes, macOS curl doesn't |
| Hackesche Höfe Kino | hoefekino.de/programm-tickets/aktuelles-programm/ | HTML (TYPO3), no JSON-LD; programme page links every film, film pages have credits + all showtimes | Allowed | **Adapter done.** Dates without year; tickets via kinoheld; 35mm and DEFA specials. The cinema's year is sometimes a re-release year (*The Zone of Interest* as 2025) or missing, so some repertory films don't count as revivals |
| Lichtblick-Kino | lichtblick-kino.org/programm/ | HTML (WordPress), no JSON-LD; monthly PDF too | Allowed | **Adapter done.** Film pages have credits + all showtimes; tickets via kinoheld; labels "Filmklassiker", "Wiederaufführung in 4K" |
| Yorck group | yorck.de/filme (+ /kinos, /filme/&lt;slug&gt;, /specials/&lt;slug&gt;) | Next.js: JSON in `__NEXT_DATA__`; all 14 cinemas' sessions on one page | Allowed (`Allow: /`) | **Adapter done** (one adapter for all 14). Listing has only the German release date, so film pages are read for revival candidates and cached. Under load the site sometimes serves film pages without data: those are warned about and retried next run |

- [~] Read each site's terms and robots.txt: robots.txt checked (and obeyed by
      the scraper) for the six sources; terms of use not read yet
- [ ] Ask cinemas directly for a feed (small repertory cinemas often welcome
      the exposure)
- [~] Impressum and DSGVO privacy policy, which a public German site needs:
      pages exist with placeholders (`[[ ... ]]`) for name, address, contact
      and the GitHub transfer basis; `reflick build` warns until they're
      filled in. Pico and Alpine are served from the site, so no CDN is
      involved

If most cinemas offer structured data or clean HTML, the project is
straightforward. If most use PDFs, ingestion will take most of the effort.

## 3. Data model

- [x] **Cinema**: name, address, neighbourhood, website
- [~] **Film**: title, original title, year and director are stored per
      screening; OMDb matches (IMDb id, title, genres) live in
      `film_matches`. There is no separate film table yet
- [x] **Screening**: cinema, start time, language/subtitles, tags, source URL,
      ticket link (Lichtblick only, not shown on the site)
- [x] **Series**: stored per screening (e.g. "Clockwork Kubrick", "Halloween
      im Kant")
- [x] Raw scraped data kept separate from cleaned data: `raw_screenings` holds
      what cinemas publish; title clean-up and OMDb data are applied at build
      time

## 4. Ingestion pipeline

- [x] One adapter per source (a cinema or a group like Yorck), all emitting
      the same screening format
- [x] A snapshot of each scrape run is stored
- [x] Alert when a source or a single cinema suddenly returns zero
      screenings: the scrape exits non-zero, the daily workflow still
      publishes and then fails, so GitHub emails a warning
- [x] Daily scheduled run: `.github/workflows/publish.yml` (04:00 UTC), with
      the database kept in the Actions cache and old runs pruned. Not run on
      GitHub yet

## 5. Film matching and enrichment

- [x] Match films to OMDb for genres and IMDb ids, cached in `film_matches`
- [~] German titles: Yorck's original titles now match (e.g. "Das
      Appartement" → *The Apartment*). Babylon and Lichtblick give no original
      title, so their German-titled films still mostly miss. Consider TMDB or
      Wikidata as a second source
- [x] Clean titles: language suffixes ("[OmU]"), series prefixes, cinema
      add-ons ("LIVE mit Babylon Orchester Berlin") shown as badges, trailing
      years
- [ ] Manual review queue for uncertain matches
- [~] Apply the revival rule: uses the cinema's year plus any cinema label.
      OMDb's year isn't used for it yet
- [ ] Titles the cinema prints in capitals ("SÜHNE") stay in capitals unless
      OMDb has the film

## 6. Storage and backend

- [x] SQLite
- [x] The site is generated statically after each scrape, with no API

## 7. Frontend

- [x] All upcoming revivals across cinemas on one page, grouped by day, late
      shows under the evening before
- [x] Date strip: one chip per day with screenings, showing how many match
      the other filters; several days can be picked (e.g. a weekend)
- [x] Filters: search, cinema, language/subtitles, genre, plus a Reset
      button
- [x] Filter: districts, multi-select (e.g. Neukölln + Kreuzberg); only
      districts with upcoming revivals are offered
- [ ] Filter: format (35mm, 4K restoration, silent film with live music:
      needs a mapping of the cinemas' different labels)
- [x] Sticky filter bar on screens wider than 576px, with day headers
      sticking below it
- [ ] Mobile filter sheet: on phones, a compact sticky bar with the search
      and a "Filters (n)" button that opens a bottom sheet with the filters
      stacked full-width, updating the list live and ending in "Show n
      screenings" and Reset. Could use a native `<dialog>`, which Pico
      already styles. Until then the filters scroll away on phones
- [ ] Film page with all upcoming screenings of one title: built, then
      removed in favour of the single page. Decide whether to bring it back
- [x] iCal feed (`reflick.ics`)
- [x] Titles link to the film's page on the cinema's site; cinema names link
      to Google Maps
- [~] Mobile-first: the layout adapts to narrow screens, but hasn't been
      checked on a real phone

## 8. Hosting and operations

- [~] Static hosting plus a scheduled job: GitHub Pages workflow ready; the
      repository, Pages setting and `OMDB_API_KEY` secret still need setting
      up on GitHub (see README, "Publishing")
- [ ] Register the domain once the name is final

## 9. MVP launch

- [ ] Launch with a handful of cinemas and a simple list that is actually
      correct
- [ ] Tell the cinemas and local film communities; consider a weekly
      newsletter

## 10. Later

- [ ] Email or RSS alerts for a director or film
- [ ] A way for cinemas to submit their own programme
- [ ] Other cities
