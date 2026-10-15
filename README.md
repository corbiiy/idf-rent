# idf-rent

A personal aggregator of **new rental listings in Île-de-France**, hosted entirely on GitHub:

- a Python crawler (`scraper/`) runs every 20 minutes in GitHub Actions and normalises each source into one schema,
- the result is committed to `data/listings.json`,
- a static site (`site/`) on GitHub Pages filters that file in the browser with Jinka's filter vocabulary,
- new listings matching `filter.json` are pushed to Telegram.

The mechanism mirrors what the Jinka app does server-side (one normalised schema, a `source` slug per ad, a saved filter, a liveness re-check of stored links). Nothing here talks to Jinka's API.

## Sources

| slug | site | how | status |
|---|---|---|---|
| `bienici` | [Bien'ici](https://www.bienici.com) | public JSON endpoint its own front end uses (`/realEstateAds.json`, `/realEstateAd.json`) | working |
| `pap` | [PAP](https://www.pap.fr) | HTML list pages (`search-list-item-alt` cards) | **blocked**: pap.fr serves a Cloudflare JavaScript challenge (HTTP 403, `cf-mitigated: challenge`) to every non-browser client, including `robots.txt` and the sitemaps. The module stops on the 403 and the run continues with the other sources. The parser is kept and unit-tested against a saved fixture so it works the day PAP exposes its pages or an RSS feed to plain clients again. |

### Excluded on purpose

- **Leboncoin** and **SeLoger**: protected by DataDome bot detection, and their terms of service forbid automated access. Working around bot detection is not something this project does.
- **Jinka's own API** (`api.jinka.fr`): private API behind user tokens; reusing it would be both against their terms and pointless (the point is to have our own feed).
- Anything a site's `robots.txt` disallows for our user agent.

Agency networks (Orpi, Century 21, Foncia, …) are the natural next sources: each needs one module in `scraper/sources/` exposing `SLUG`, `LABEL`, `fetch()` and `is_live()`.

## Crawler etiquette

- One plain, identifiable user agent (`scraper/http.py`).
- `robots.txt` is fetched once per host and respected.
- A fixed delay between requests (1.5 s), at most two list pages per department and source per run.
- **HTTP 403 or 429 stops that source for the run. No retries, no header spoofing, no challenge solving.**
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

Deduplication: by URL, then by `(rent, int(area), postal_code)` plus a matching first-photo dHash (Hamming distance ≤ 6).

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
4. **Telegram secrets** (Settings → Secrets and variables → Actions → New repository secret):
   - `TELEGRAM_BOT_TOKEN`: create a bot with [@BotFather](https://t.me/BotFather) (`/newbot`), copy the token.
   - `TELEGRAM_CHAT_ID`: send any message to your bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `message.chat.id`. For a group, add the bot to the group and use the (negative) group id.
   Without these secrets the workflow still runs; matching listings are printed in the job log instead.
5. Edit `filter.json` to taste (same keys as the site's filters: `rent_min`, `rent_max`, `area_min`, `area_max`, `room_min`, `bedroom_min`, `furnished` yes/no/ns, `owner_type` Particulier/Agence/ns, `dpe` list, `sources` list, `where.dpts` department codes, `where.postalCodes`). `"ns"` or a missing key means not specified.
6. Run the crawl once by hand: Actions → *Crawl rentals* → *Run workflow*. It then runs every 20 minutes (GitHub may delay scheduled runs by a few minutes, and pauses schedules on repositories with no activity for 60 days).

## Site

`site/index.html` + `app.js` + `style.css`, no build step. Filters: rent and area min/max, rooms and bedrooms minimum (`1+`…`5+`), furnished, owner type, DPE classes, zone picker over the 8 IDF departments plus free postal codes, sources, sort. The filter is saved in `localStorage`. The page also stores the timestamp of your last visit and marks listings first seen after it with a **Nouveau** badge (and a "only new" toggle). Each card shows the source label and links to the original ad.

## Layout

```
scraper/            Python package (python -m scraper)
  model.py          Listing dataclass, IDF departments
  http.py           PoliteSession: user agent, robots.txt, delay, stop on 403/429
  sources/          one module per source (bienici.py, pap.py)
  dedupe.py         URL + fingerprint + photo dHash
  store.py          load/merge/liveness/prune/save data/listings.json
  notify.py         filter.json matching and Telegram
tests/              unittest suite with a saved PAP list fixture
data/listings.json  crawler output (committed by the workflow)
site/               static front end for GitHub Pages
filter.json         the saved alert used for Telegram
.github/workflows/  crawl.yml (cron */20) and pages.yml
```
