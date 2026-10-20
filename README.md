# idf-rent

A personal aggregator of **new rental listings in Île-de-France**, hosted entirely on GitHub:

- a Python crawler (`scraper/`) normalises each source into one schema; it runs as an always-on worker on Railway every 5 minutes (or, without Railway, from a GitHub Actions cron),
- the result is committed to `data/listings.json` on the `data` branch of this repository (`main` only carries code and a snapshot for local development),
- a static site (`site/`) on GitHub Pages reads that file straight from the repository and filters it in the browser with Jinka's filter vocabulary,
- new listings matching `filter.json` are posted to a Discord channel through a webhook.

The mechanism mirrors what the Jinka app does server-side (one normalised schema, a `source` slug per ad, a saved filter, a liveness re-check of stored links). Nothing here talks to Jinka's API.

## Sources

Thirteen modules in `scraper/sources/`, one per site, all reading public search pages with a plain user agent and the rules below. Status on 2026-10-16; the live per-source status (count, last success, last error) is in the `sources` block of `data/listings.json` and shown on the site.

| slug | site | kind | how | status |
|---|---|---|---|---|
| `bienici` | [Bien'ici](https://www.bienici.com) | portal | public JSON endpoint its front end uses (`/realEstateAds.json`), per department | working |
| `locservice` | [LocService](https://www.locservice.fr) | private owners | HTML list per department (`/<dept>/location-<name>.html`, `-pN`) | working |
| `paruvendu` | [Paruvendu](https://www.paruvendu.fr) | portal, owners and agencies | HTML list per department and kind (`?p=N`); one ad-page GET per never-seen ad outside Paris to get the postal code | working |
| `pap` | [PAP](https://www.pap.fr) | private owners | HTML list per department (`-g<id>-N`) | intermittent: Cloudflare challenge (HTTP 403) on most requests; retried hourly, stops cleanly on 403 |
| `era` | [ERA](https://www.eraimmobilier.com) | agency network | Angular transfer state embedded in `/location-<kind>/ile-de-france-1/<dept>` | working |
| `foncia` | [Foncia](https://fr.foncia.com) | agency network | Angular transfer state embedded in `/location/<dept>/page-N` (no query strings: robots.txt forbids them) | working |
| `ladresse` | [L'Adresse](https://www.ladresse.com) | agency network | HTML list per department and kind (`/recherche/location/<kind>/<dept>/N`), lat/lng from the map script | working |
| `iad` | [iad France](https://www.iadfrance.fr) | mandataire network | HTML list per department (`/annonces/<dept>/location?page=N`) | working |
| `laforet` | [Laforêt](https://www.laforet.com) | agency network | national HTML list (`/louer/location-<kind>?page=N`), newest first, filtered to IDF postal codes | working |
| `century21` | [Century 21](https://www.century21.fr) | agency network | HTML list per department and kind (`/annonces/location-<kind>/d-<dept>/page-N/`); one ad-page GET per never-seen ad outside Paris to get the postal code | working |
| `lodgis` | [Lodgis](https://www.lodgis.com) | furnished rentals, Paris only | 20 arrondissement category pages (`?p=N`), hourly | working |
| `arthurimmo` | [Arthurimmo](https://www.arthurimmo.com) | agency network | region page `/immobilier/location/immo-ile-de-france/bien-<kind>?sort=-created_at&page=N` (2.5 MB pages), every 30 min | working |
| `orpi` | [Orpi](https://www.orpi.com) | agency network | the search page embeds the whole department result set as JSON (`data-result` attribute); one GET per department, every 30 min | working |

Per-field coverage differs by site: DPE comes from Bien'ici, PAP, Paruvendu, ERA, Foncia; coordinates from Bien'ici, ERA, L'Adresse, Orpi; posting dates from Bien'ici, ERA, Foncia, Orpi, Paruvendu (last-update date). Agency-network ads are tagged `owner_type: Agence`, LocService and PAP `Particulier`, Paruvendu per card.

Adding a source is one module exposing `SLUG`, `LABEL`, `COLOR`, optional `MIN_INTERVAL`, `fetch()` and `is_live()` (see `scraper/sources/__init__.py`), a trimmed fixture under `tests/fixtures/` and a unittest. Modules are discovered automatically; a failing or blocked source records `last_error` in the status block and never stops the others.

### Excluded on purpose

- **Leboncoin** and the **SeLoger group** (SeLoger, Logic-Immo, Belles Demeures): court-protected databases (rulings against Jinka in December 2025 and April 2026), DataDome-guarded, and their terms forbid automated access. Not crawled, not proxied.
- **Jinka's own API** (`api.jinka.fr`): private, behind user tokens.
- Anything a site's `robots.txt` disallows for our user agent.

### Surveyed on 2026-10-16 and not implemented

Each of these was re-checked in a real browser to see which endpoint its own front end calls, and that endpoint was then tried with a plain client. Nothing here is worked around: a site that only answers a browser stays out.

| site | why not |
|---|---|
| Figaro Immobilier | Cloudflare managed challenge on every path (even `robots.txt`) for non-browser clients |
| AvendreAlouer | DataDome bot protection |
| Efficity | challenge for non-browser clients, `robots.txt` forbids our client, and the rental page redirects to an agent directory |
| Maisons & Appartements | Cloudflare "verifying your browser" interstitial, shown even to a real browser |
| Stéphane Plaza, Sixième Avenue | listings come from a `/search-goods` JSON call that Cloudflare's WAF answers with 403 for non-browsers; inventories are 1 and 2 rentals in Paris anyway |
| Guy Hoquet | hash-routed search app whose results never appear as an observable request (only a location autocomplete); no server-side list |
| Nestenn | the only result page, `/listing`, is disallowed by `robots.txt`; the static `/location-appartement` pages show six featured ads nationwide |
| Breteuil | site unreachable (also from a browser) |
| Ouest-France Immo | `robots.txt` disallows `/louer/` and `/annonce/`; little IDF stock anyway |
| Barnes, Emile Garcin, Engel & Völkers | `robots.txt` disallows their search pages, or listings load only client-side; luxury segment |
| Studapart, Immojeune | public pages list student residences, not individual ads |
| Flatlooker (now Manda), SuperImmo | no public listing index found |
| Colonies, Daniel Féau | site unreachable |
| Gens de confiance | members only |

## Crawler etiquette

- One plain, identifiable user agent (`scraper/http.py`).
- `robots.txt` is fetched once per host and respected.
- A fixed delay between requests (1.5 s), at most two list pages per department and source per run (one on Railway).
- **HTTP 403 or 429 stops that source for the run. No retries, no header spoofing, no challenge solving.**
- Each cycle has a time budget (`CYCLE_BUDGET`, 240 s on Railway): sources are crawled least-recently-run first and the ones not reached go first next cycle, so twelve sources fit a 5-minute loop without hammering anyone. Heavy or flaky sources declare a `MIN_INTERVAL` (PAP and Lodgis hourly, Arthurimmo every 30 min).
- Photos are fetched only once per new ad, to compute a perceptual hash for cross-source dedupe.

## Data model

`data/listings.json`:

```json
{
  "generated_at": "2026-10-15T18:36:04+00:00",
  "count": 100,
  "sources": {"bienici": {"label": "Bien'ici"}, "pap": {"label": "PAP"}},
  "listings": [ { "id": "bienici:ag923721-554347664", "source": "bienici", "url": "…", "title": "…",
                  "rent": 2500, "charges": 300, "area": 73, "rooms": 3, "bedrooms": 2, "furnished": true,
                  "owner_type": "Agence", "dpe": "D", "postal_code": "92110", "city": "Clichy",
                  "lat": 48.9, "lng": 2.3, "photos": ["…"], "posted_at": "…", "first_seen": "…",
                  "last_seen": "…", "expired": false, "photo_hash": "dhash:…" } ]
}
```

`rent` is the monthly rent charges included; `owner_type` is `Particulier` or `Agence`; `dpe` is `A`–`G`.

Deduplication: by URL, then by `(rent, int(area), postal_code)` plus either a matching first-photo dHash (Hamming distance ≤ 6) or matching coordinates rounded to ~100 m, which catches the same agency ad syndicated to several networks and portals.

Liveness: each run re-checks up to 60 stored ads not seen in the last 6 hours. HTTP 404/410 (or Bien'ici's `onTheMarket: false`) marks the ad `expired`. Expired ads are kept 14 days so the site can show them greyed out, then pruned.

## Local setup

```bash
python3 -m pip install -r requirements.txt
python3 -m scraper --departments 92 --pages 1      # crawl one department
python3 -m unittest                                  # parser, dedupe and filter tests
python3 -m http.server 8765                          # then open http://127.0.0.1:8765/site/
```

`python -m scraper --help` lists the flags (`--sources`, `--no-liveness`, `--no-photo-hash`, `--notify`).

## GitHub setup

1. Push this repository (public is fine: it contains only public ads and no secrets).
2. **Pages**: Settings → Pages → Source: *GitHub Actions*. The `pages.yml` workflow deploys `site/` plus `data/listings.json` on every push that changes them.
3. **Actions permissions**: Settings → Actions → General → Workflow permissions: *Read and write* (the crawl workflow commits `data/listings.json` back).
4. **Discord webhook** (Settings → Secrets and variables → Actions → New repository secret):
   - In Discord, open the target channel → Edit channel → Integrations → Webhooks → New webhook → Copy webhook URL.
   - Save it as the repository secret `DISCORD_WEBHOOK_URL`.
   Without this secret the workflow still runs; matching listings are printed in the job log instead. Each run posts at most 20 listings (10 embeds per message, each with photo, rent, specs, place and the link to the original ad) plus a one-line count of the rest.
5. Edit `filter.json` to taste. The committed one alerts on rents up to 1050 € in Paris and 750 € elsewhere (`rent_max` is the default cap, `rent_max_by_dpt` overrides it per department), 14 m² and more, in an explicit list of 47 postal codes (all of Paris plus selected towns in 91, 92 and 94); with `where.dpts` empty, a listing must carry one of those postal codes to alert. Keys are the same as the site's filters: `rent_min`, `rent_max`, `rent_max_by_dpt` {department: cap}, `area_min`, `area_max`, `room_min`, `bedroom_min`, `furnished` yes/no/ns, `owner_type` Particulier/Agence/ns, `dpe` list, `sources` include list, `blocked_sources` exclude list (Jinka's "sources exclues"), `where.dpts` department codes, `where.postalCodes`). `"ns"` or a missing key means not specified.
6. Run the crawl once by hand: Actions → *Crawl rentals* → *Run workflow* (tick *test_alert* to post the 3 latest matches and check the webhook).

## Running the crawler on Railway (every 5 minutes)

`scraper/worker.py` is a long-running loop: crawl, post new matches to Discord, and commit `data/listings.json` to the `data` branch through the GitHub API at most every 15 minutes. The branch is created from `main` on first run. Data lives on its own branch because Railway redeploys the service on every push to `main`. `railway.json` holds the start command; Nixpacks builds it from `requirements.txt` and `.python-version`.

1. Create a **fine-grained GitHub token**: GitHub → Settings → Developer settings → Fine-grained tokens → Generate. Repository access: only `idf-rent`. Permissions: *Contents: Read and write*. Copy it.
2. Railway → New project → *Deploy from GitHub repo* → `idf-rent`. Railway detects `railway.json`; no public port is needed (it is a worker, not a web service).
3. Service → Variables:
   - `GITHUB_TOKEN` = the token from step 1
   - `DISCORD_WEBHOOK_URL` = the same webhook URL as the GitHub secret
   - optional: `CRAWL_INTERVAL` (seconds, default `300`), `PUSH_INTERVAL` (default `900`), `CRAWL_PAGES` (default `1`), `DEPARTMENTS`, `SOURCES`, `GITHUB_REPO` (default `corbiiy/idf-rent`), `GITHUB_BRANCH` (default `data`)
4. Deploy. The log should show `synced data/listings.json from …`, then one `cycle: …` line per interval and `pushed data/listings.json as …` every 15 minutes. Railway redeploys on every push to `main`, and the worker re-reads the repository copy on start, so nothing is lost across restarts.

While Railway runs, the GitHub cron in `crawl.yml` stays commented out so two crawlers never commit the same file. If you stop using Railway, uncomment the `schedule:` block to go back to the 20-minute GitHub crawl.

Why not crawl faster than 5 minutes: Bien'ici publishes a few hundred Île-de-France rentals a day, so a 5-minute loop already sees each ad within minutes of publication; a tighter loop only adds load on their side.

## Site

`site/index.html` + `app.js` + `style.css`, no build step. On GitHub Pages the page fetches `data/listings.json` from the `data` branch via `raw.githubusercontent.com` (fresh within about 5 minutes of a commit), so the site only redeploys when `site/` changes; on a local server it reads the file from the checkout. Filters: rent and area min/max, rooms and bedrooms minimum (`1+`…`5+`), furnished, owner type, DPE classes, zone picker over the 8 IDF departments plus free postal codes, sort. The sources panel lists every source with its active count and last crawl status; unticking one excludes it (saved locally). The filter is saved in `localStorage`. The page also stores the timestamp of your last visit and marks listings first seen after it with a **Nouveau** badge (and a "only new" toggle). Each card shows the source label and links to the original ad.

## Layout

```
scraper/            Python package (python -m scraper)
  model.py          Listing dataclass, IDF departments
  http.py           PoliteSession: user agent, robots.txt, delay, stop on 403/429
  sources/          one module per source (12 sites, auto-discovered)
  dedupe.py         URL + fingerprint + photo dHash
  store.py          load/merge/liveness/prune/save data/listings.json
  notify.py         filter.json matching and Discord webhook
  run.py            one crawl cycle (shared by the CLI and the worker)
  worker.py         always-on loop for Railway: crawl, notify, push data via the GitHub API
  github.py         Git Data API client used by the worker
tests/              unittest suite with a saved PAP list fixture
data/listings.json  crawler output (live copy on the `data` branch; `main` holds a snapshot)
site/               static front end for GitHub Pages
filter.json         the saved alert used for Discord alerts
.github/workflows/  crawl.yml (manual / fallback cron) and pages.yml
railway.json        Railway start command for the worker
```
