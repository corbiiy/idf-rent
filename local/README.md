# Local leboncoin watcher

leboncoin is not crawled by the Railway worker and never will be: its listings database is
legally protected (aggregators were condemned for extracting it) and the site runs DataDome
bot protection. This folder is a different thing: a **personal watcher that runs on your
Mac, inside your own leboncoin browser session**, re-opens the searches you built on the
site every few minutes the way you would by hand, and posts the ads you have not seen yet to
your Discord channel.

What it does not do, on purpose: no proxy, no user-agent or fingerprint change, no headless
tricks, no captcha solving, no retries when the site objects, no publishing. leboncoin ads
stay on this machine; they are never pushed to the repository or the public site.

If leboncoin shows a verification page, the cycle stops, you get one Discord message, and you
solve it yourself in the watcher window. Using the site this way may still be against its
terms of service; that is your call to make, for your own account.

## Setup (once)

```bash
cd /path/to/idf-rent
python3 -m pip install --user playwright requests Pillow
python3 -m playwright install chromium
```

1. **Log in once.** Opens a Chromium window with a persistent profile stored under
   `~/Library/Application Support/idf-rent/leboncoin-profile`. Log in, deal with the cookie
   banner, then press Enter in the terminal.
   ```bash
   python3 local/leboncoin_watch.py --login
   ```
2. **Create your searches.** On leboncoin.fr, in your normal browser, open *Immobilier →
   Locations*, set the filters you want (postal codes or cities, maximum rent, minimum
   surface, furnished or not, sort by *Plus récentes*), then copy the address bar. Put each
   URL in `local/leboncoin_searches.json` (copy `leboncoin_searches.example.json`). One search
   per area keeps every page short.
3. **Secrets.** Copy `local/.env.example` to `local/.env` and paste your Discord webhook URL
   (the same one the Railway worker uses). The file is git-ignored.
4. **Test one cycle** without posting anything:
   ```bash
   python3 local/leboncoin_watch.py --once --dry-run
   ```
   The first cycle only records what is already on the page; alerts start with the next one.
   Matches are printed; the Discord filter is the repository's `filter.json` (postal codes,
   per-department rent cap, minimum surface and rooms), exactly as for the other sources.

## Run at login (launchd)

```bash
mkdir -p ~/Library/Logs/idf-rent
sed -e "s|__REPO__|$(pwd)|g" -e "s|__HOME__|$HOME|g" local/com.idf-rent.leboncoin.plist \
  > ~/Library/LaunchAgents/com.idf-rent.leboncoin.plist
launchctl load ~/Library/LaunchAgents/com.idf-rent.leboncoin.plist
```

- Logs: `tail -f ~/Library/Logs/idf-rent/leboncoin.log`
- Stop: `launchctl unload ~/Library/LaunchAgents/com.idf-rent.leboncoin.plist`
- The Chromium window must stay open (minimise it, do not close it); the agent restarts the
  watcher if it exits with an error.

## Files on this machine

| path | content |
|---|---|
| `~/Library/Application Support/idf-rent/leboncoin-profile/` | the browser profile with your session |
| `~/Library/Application Support/idf-rent/leboncoin-seen.json` | ids already seen (delete it to start over; the next first cycle alerts nothing) |
| `~/Library/Application Support/idf-rent/leboncoin-listings.json` | local archive of every ad seen, same schema as `data/listings.json` |
| `~/Library/Application Support/idf-rent/debug/` | a copy of any results page where no ad could be parsed |

## How the page is read

`leboncoin_parse.py` prefers the `__NEXT_DATA__` JSON the page embeds (ads are found by
walking the JSON for objects with `list_id` and `subject`, so the exact path does not matter)
and falls back to the rendered cards. It is unit-tested against a synthetic fixture
(`tests/fixtures/leboncoin_next_data.html`), not against real ads. If leboncoin changes its
page and a cycle parses zero ads, the page is saved under `debug/` so the selectors can be
adjusted; the watcher does not retry.

Cadence: default 300 s between cycles, floor 180 s, a few seconds between two searches,
plus a little jitter.
