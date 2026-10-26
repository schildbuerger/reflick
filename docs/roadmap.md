# Roadmap

Ordered so the risky parts surface early. Status as of 2026-10-25:
`[x]` done, `[~]` partly done, `[ ]` open.

## 1. Define scope

- [x] Fix the revival rule: the film's year is at least 5 years ago, or the
      cinema labels it a re-release (see README)
- [x] Choose the first cinemas: Arsenal, Babylon Mitte, Hackesche Höfe Kino,
      Lichtblick-Kino, Zeughauskino and the 14 Yorck cinemas; from a survey of
      further candidates (2026-10-25) Brotfabrik Kino, Bundesplatz-Kino,
      Filmkunst 66, Il Kino, Kino Krokodil and Sinema Transtopia

## 2. Survey data sources and legal side

For each cinema, record how its programme is published. This decides how hard
each scraper will be.

| Cinema | Programme URL | Format (JSON-LD / API / iCal / PDF / HTML) | robots.txt / terms OK? | Notes |
| --- | --- | --- | --- | --- |
| Arsenal | arsenal-berlin.de/kalender/ (now in Wedding, Plantagenstraße 30) | JSON API behind the calendar (`/api/v1/search/calendar/`, TYPO3 Solr, 12 events a page) with credits, format, language, series and ticket link | robots.txt returns 404 (no rules) | **Adapter done.** Dates without year. Foyer events are installations and skipped. Tickets via kinotickets.express |
| Zeughauskino | dhm.de/zeughauskino/spielplan/ | HTML (TYPO3 Solr listing, 10 a page) with ISO start time, series, country/year, format, sometimes language | Allowed | **Adapter done.** Listing runs on into placeholder dates (2064) after the real programme, so paging stops 180 days ahead. Screenings with guests lack facts in the listing; their pages are read and cached. macOS curl rejects the certificate chain, Python/httpx doesn't. Tickets via cinetixx |
| Brotfabrik Kino | brotfabrik-berlin.de/kino/ | JSON API of The Events Calendar (`/wp-json/tribe/events/v1/events?categories=kino`, 50 a page) with full start time, ticket link and a credits line in the description; iCal and JSON-LD too | Allowed (`Disallow:` empty); Impressum has no usage clause | **Adapter done.** Venue with stage and gallery too, so only the "kino" category is read. The API's next-page link drops that filter, so page URLs are built by the adapter. Tickets via weeztix |
| Babylon Mitte | babylonberlin.eu/programm | HTML (Joomla), no JSON-LD; whole programme on one page, one `li.mix` per screening with full timestamp | Allowed | **Adapter done.** Credit line is cut off, so film pages are read when the year is missing. Also lists theatre and readings (skipped). Server omits its intermediate certificate: Python/httpx copes, macOS curl doesn't |
| Hackesche Höfe Kino | hoefekino.de/programm-tickets/aktuelles-programm/ | HTML (TYPO3), no JSON-LD; programme page links every film, film pages have credits + all showtimes | Allowed | **Adapter done.** Dates without year; tickets via kinoheld; 35mm and DEFA specials. The cinema's year is sometimes a re-release year (*The Zone of Interest* as 2025) or missing, so some repertory films don't count as revivals |
| Lichtblick-Kino | lichtblick-kino.org/programm/ | HTML (WordPress), no JSON-LD; monthly PDF too | Allowed | **Adapter done.** Film pages have credits + all showtimes; tickets via kinoheld; labels "Filmklassiker", "Wiederaufführung in 4K" |
| Sinema Transtopia | sinematranstopia.com/de/calendar | HTML calendar (Laravel) with start time, series, title + second title, director, country, year, cinetixx ticket link; film pages add runtime and language | Allowed (only `/page/data-confidentiality` disallowed); imprint has no usage clause | **Adapter done.** bi'bak's cinema in Wedding, strong on restorations ("Film Restored"). `<time>` elements claim UTC for Berlin times, so the printed time is read. Sets a cookie with a non-ASCII name, which broke follow-up requests until the Fetcher stopped keeping cookies. HANE Salon talks skipped |
| Bundesplatz-Kino | bundesplatz-kino.de/spielplan.php | Hand-made PHP: Spielplan by day with times and film links (film.php?mid=), own reservation; film pages with "BRD/Frankreich 1955 \| 133 Min." and "Regie:" | Allowed (only the guestbook script disallowed); no usage clause | **Adapter done.** Unclosed tags nest the day sections, so rows are dated by the heading above them. Language version and often the year are part of the title. Film pages kept in the page cache for a month |
| Kino Krokodil | kino-krokodil.de/programm/ | WordPress: programme links film pages, which list all dates (kinoheld ticket links) and the credits ("Deutschland 2026, 122 min, deutsche Originalfassung", "Regie: ...") | Allowed (`Disallow:` empty); no usage clause | **Adapter done.** Central and Eastern European films, with Czech and Slovak classics. Times claim UTC like Transtopia's. Programmes of several films take the first film's year and director |
| Il Kino | ilkino.de/movie-program | Schema.org JSON-LD: ScreeningEvents (time, duration, subtitles, kinoheld ticket link) and Movies (director, year, language) | robots.txt returns 404 (no rules); only the usual copyright notice | **Adapter done.** One request per run. Language version follows from the subtitles. Mostly current releases, no revivals at the moment |
| Filmkunst 66 | filmkunst66.de/programm | Programme shown only in kinoheld's widget (off-limits, see below), but the cinema's own weekly flyer is a PDF with a table per screen | robots.txt returns 404 (no rules); no usage clause | **Adapter done.** The PDF is read with pypdf's layout mode, which keeps the weekday columns; titles can run over two lines. Covers the current week only, and gives no credits beyond a year in some titles. Repertory series "Frühe Meister der Filmkunst" |
| Wolf Kino | wolfberlin.org | Kirby CMS; film pages have credits, but showtimes come only from kinoheld's API (with a key in the site's script) | robots.txt returns 404; no usage clause | **Not used:** reading kinoheld's API is off-limits (see below). Only event pages have times in the HTML |
| Yorck group | yorck.de/filme (+ /kinos, /filme/&lt;slug&gt;, /specials/&lt;slug&gt;) | Next.js: JSON in `__NEXT_DATA__`; all 14 cinemas' sessions on one page | Allowed (`Allow: /`) | **Adapter done** (one adapter for all 14). Listing has only the German release date, so film pages are read for revival candidates and cached. Under load the site sometimes serves film pages without data: those are warned about and retried next run |

- [x] Read each site's terms and robots.txt: robots.txt checked (and obeyed by
      the scraper) for the six sources. None of the legal pages mention
      automated access; most only have a general copyright notice, and Yorck
      offers its site "zum persönlichen Gebrauch". Permission is asked for
      below
- [~] Ask cinemas for permission to use their programme data, and for a
      feed if they have one (small repertory cinemas often welcome the
      exposure): requests sent by email on 2026-10-25, waiting for replies.
      Still to ask: b-ware! Ladenkino, for a feed of its repertory specials
      (see below)
- [~] Impressum and DSGVO privacy policy, which a public German site needs:
      pages exist with placeholders (`[[ ... ]]`) for name, address, contact
      and the GitHub transfer basis; `reflick build` warns until they're
      filled in. Pico and Alpine are served from the site, so no CDN is
      involved

- [~] More cinemas, from a survey of 22 candidates (2026-10-25) by repertory
      share, data format and the terms on their legal pages. Low risk, now
      with adapters (2026-10-25, see the table): Il Kino, Kino Krokodil,
      Filmkunst 66, Bundesplatz-Kino and Sinema Transtopia. Wolf Kino turned
      out to load its showtimes only from kinoheld's API, so it's left out.
      Only with permission, as their Impressum forbids
      storing content in databases: City Kino Wedding, Moviemento, Kino
      Toni. Mostly current releases, so not worth it for now: fsk, Sputnik,
      b-ware!, Tilsiter, Filmrauschpalast, Eva, Union, Kino Zukunft, and
      Klick Kino (PDF programme)
- [x] Checked two more by hand (2026-10-25), neither worth an adapter now.
      Both allow crawling in robots.txt, and neither's legal pages forbid it
      (Ladenkino has only the usual copyright notice), but both publish
      their regular showtimes only through kinoheld's booking widget:
      - Kino Intimes (Friedrichshain): mostly current releases, a few
        revival specials and a monthly horror night ("Fright Night"). Film
        pages have credits but no showtimes; those are in the widget and a
        weekly PDF
      - b-ware! Ladenkino (Friedrichshain, the "b-ware!" above): ~20 films a
        day, mostly current, but strong repertory specials (a 30-film
        Halloween marathon of horror classics, a jazz series). Specials are
        blog posts with times but no years or directors, so the revival
        rule and the Wikidata/OMDb lookup can't work on them; worth asking
        for a feed instead
- [x] Kinoheld (ticket platform of Kino Intimes, b-ware!, Hackesche Höfe,
      Lichtblick) is off-limits as a source without its written
      permission: its terms (kinoheld.de/agb, 4.7 and 4.8) forbid robot or
      spider software and copying, monitoring or processing the site or its
      content, also through the booking widgets embedded on cinema sites,
      and 4.9 threatens legal steps. Showtimes there load from an
      undocumented GraphQL API anyway. Existing adapters only read the
      cinemas' own pages, at most storing a kinoheld ticket link. A cinema
      may still send its own programme, as the data is the cinema's

If most cinemas offer structured data or clean HTML, the project is
straightforward. If most use PDFs, ingestion will take most of the effort.

## 3. Data model

- [x] **Cinema**: name, address, neighbourhood, website
- [x] **Film**: the `films` table keeps each cinema's credits (year,
      director, original title, country) for good, by the cinema's own key,
      so a film that returns needs no new page request (Yorck, Babylon).
      Wikidata (`film_titles`) and OMDb (`film_matches`) results are kept
      for good too, by title and year. Screenings still carry their own
      copy of the credits, as published
- [x] **Screening**: cinema, start time, language/subtitles, tags, source URL,
      ticket link (where the cinema gives one, not shown on the site)
- [x] Language versions unified to OV, OmeU, OmdU, DF and oD (`languages.py`);
      versions the rules can't read are shown as printed and added to
      `OUTLIERS` one by one
- [x] **Series**: stored per screening (e.g. "Clockwork Kubrick", "Halloween
      im Kant")
- [x] Raw scraped data kept separate from cleaned data: `raw_screenings` holds
      what cinemas publish; title clean-up, language codes, Wikidata and OMDb data
      are applied at build time

## 4. Ingestion pipeline

- [x] One adapter per source (a cinema or a group like Yorck), all emitting
      the same screening format
- [x] A snapshot of each scrape run is stored
- [x] Alert when a source or a single cinema suddenly returns zero
      screenings: the scrape exits non-zero, the daily workflow still
      publishes and then fails, so GitHub emails a warning
- [~] Daily scheduled run: `.github/workflows/publish.yml` (02:33 UTC, i.e.
      03:33 Berlin time in winter), with the database kept in the Actions
      cache and old runs pruned. Runs on push and by hand work, but with
      `timezone: Europe/Berlin` in the schedule it never fired (2026-10-25 and
      -26, no GitHub incident), so it's plain UTC since 2026-10-26; a
      scheduled run is still to be confirmed

## 5. Film matching and enrichment

- [x] Match films to OMDb for genres and IMDb ids, cached in `film_matches`
- [x] German and original titles from Wikidata (no key), shown on the site
      German first. Wikidata's IMDb ids let OMDb find German-titled films: in
      a first run 96 of 102 films matched, and OMDb found 19 films it had
      missed before
- [x] Clean titles: language suffixes ("[OmU]"), series prefixes, cinema
      add-ons ("LIVE mit Babylon Orchester Berlin") shown as badges, trailing
      years
- [x] Apply the revival rule: uses Wikidata's first release year for matched
      films, else the cinema's, plus any cinema label. (OMDb's year was tried
      first, but it's the US release: Aguirre 1977, not 1972.) Only revival
      candidates by the cinema's year are looked up, so Wikidata's year can
      drop a film but not add one

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
- [x] Language and genre options can also be ruled out with a ✕ next to
      each (e.g. "not Documentary"), instead of picking all the others
- [x] Filter: popularity (well known, lesser known, rarely seen, unknown),
      from IMDb vote counts via OMDb
- [x] Filter: districts, multi-select (e.g. Neukölln + Kreuzberg); only
      districts with upcoming revivals are offered
- [x] Sticky filter bar on screens wider than 576px, with day headers
      sticking below it
- [x] Filters on phones: they scroll away with the page, and a back-to-top
      button (bottom right, shown after two screen heights) brings them back.
      Chosen over a sticky filter bar with a bottom sheet, to keep it simple
- [x] Screenings that have started are hidden in the browser, also while the
      page stays open, since the site is built only once a day. Days read
      "Today" and "Tomorrow"
- [x] iCal feed (`reflick.ics`)
- [x] A Details button links to the film's page on the cinema's site; cinema
      names link to Google Maps; matched films link to Letterboxd
- [x] Mobile-first: the layout adapts to narrow screens, checked on a real
      phone
- [x] Every other screening row of a day has a faint stripe; rows hidden by
      the filters don't count, so the visible ones keep alternating
- [~] Map view (List/Map switch at the right of the date strip; every visit
      starts with the list): an outline map of
      Berlin drawn into the page (districts, rivers, Ringbahn; no tiles, no
      third party), with a pin per cinema that follows the filters. Pins of
      cinemas showing something today light up with the number of today's
      screenings; cards below list each cinema's next screenings, today's
      highlighted. Zoomable up to 4× (pinch, wheel or +/−) and draggable.
      "Near me" by the location button or a tap on the map,
      computed in the browser only. Built and tested in code; still to check
      in a real browser and on a phone

## 8. Hosting and operations

- [x] Static hosting plus a scheduled job: live on GitHub Pages at
      schildbuerger.github.io/reflick/, with the `OMDB_API_KEY` secret set
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
