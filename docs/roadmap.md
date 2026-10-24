# Roadmap

Ordered so the risky parts surface early. Status as of 2026-10-24:
`[x]` done, `[~]` partly done, `[ ]` open.

## 1. Define scope

- [x] Fix the revival rule: the film's year is at least 5 years ago, or the
      cinema labels it a re-release (see README)
- [x] Choose the first cinemas: Babylon Mitte, Lichtblick-Kino and the 14
      Yorck cinemas
- [ ] Decide whether a cinema's label alone should count for recent films
      (Yorck files e.g. *Bottoms* (2023) under "Klassiker")

## 2. Survey data sources and legal side

For each cinema, record how its programme is published. This decides how hard
each scraper will be.

| Cinema | Programme URL | Format (JSON-LD / API / iCal / PDF / HTML) | robots.txt / terms OK? | Notes |
| --- | --- | --- | --- | --- |
| Arsenal | arsenal-berlin.de/kalender/ | HTML (TYPO3), no JSON-LD on homepage | robots.txt returns 404 | Not started |
| Zeughauskino | | | | Not surveyed: its site failed certificate checks from the dev sandbox |
| Babylon Mitte | babylonberlin.eu/programm | HTML (Joomla), no JSON-LD; whole programme on one page, one `li.mix` per screening with full timestamp | Allowed | **Adapter done.** Credit line is cut off, so film pages are read when the year is missing. Also lists theatre and readings (skipped). Server omits its intermediate certificate: Python/httpx copes, macOS curl doesn't |
| Lichtblick-Kino | lichtblick-kino.org/programm/ | HTML (WordPress), no JSON-LD; monthly PDF too | Allowed | **Adapter done.** Film pages have credits + all showtimes; tickets via kinoheld; labels "Filmklassiker", "Wiederaufführung in 4K" |
| Yorck group | yorck.de/filme (+ /kinos, /filme/&lt;slug&gt;, /specials/&lt;slug&gt;) | Next.js: JSON in `__NEXT_DATA__`; all 14 cinemas' sessions on one page | Allowed (`Allow: /`) | **Adapter done** (one adapter for all 14). Listing has only the German release date, so film pages are read for revival candidates and cached. Under load the site sometimes serves film pages without data: those are warned about and retried next run |

- [~] Read each site's terms and robots.txt: robots.txt checked (and obeyed by
      the scraper) for the three sources; terms of use not read yet
- [ ] Ask cinemas directly for a feed (small repertory cinemas often welcome
      the exposure)
- [ ] Impressum and DSGVO privacy policy, which a public German site needs.
      The privacy policy must cover the CDN-hosted Pico CSS and Alpine.js (or
      serve them from the site itself)

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
- [~] Alert when a source or a single cinema suddenly returns zero
      screenings: warnings on stderr and a non-zero exit code. Nothing sends
      a notification yet
- [ ] Daily scheduled run

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
- [ ] "This week" view or a way to jump to a day
- [x] Filters: search, cinema, language/subtitles, genre, plus a Reset
      button
- [x] Filter: districts, multi-select (e.g. Neukölln + Kreuzberg); only
      districts with upcoming revivals are offered
- [ ] Filter: format (35mm, 4K restoration, silent film with live music:
      needs a mapping of the cinemas' different labels)
- [ ] Film page with all upcoming screenings of one title: built, then
      removed in favour of the single page. Decide whether to bring it back
- [x] iCal feed (`reflick.ics`)
- [x] Titles link to the film's page on the cinema's site; cinema names link
      to Google Maps
- [~] Mobile-first: the layout adapts to narrow screens, but hasn't been
      checked on a real phone

## 8. Hosting and operations

- [ ] Static hosting plus a scheduled job (small VPS cron or GitHub Actions)
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
