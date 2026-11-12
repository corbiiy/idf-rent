# idf-rent · leboncoin alerts (Chrome extension)

leboncoin is not crawled by the Railway worker and never will be: its listings database is
legally protected and the site runs DataDome bot protection. This extension is a different
thing. It runs in **your own everyday Chrome**, re-opens the rental searches **you** built on
leboncoin.fr every few minutes in pinned, muted tabs, exactly as you would by hand, and posts
the ads you have not seen yet to your Discord channel through the same filter as the other
sources (`filter.json` at the root of this repository, fetched from GitHub every hour).

What it does not do: no proxy, no header or fingerprint change, no captcha solving, no
DevTools protocol, no retries when the site objects, no publishing. leboncoin ads stay in
your browser. If leboncoin shows a verification page, the cycle stops, you get one Discord
message per hour at most, the icon shows "!", and you solve it yourself in the pinned tab.
Using the site this way may still be against its terms of service; that is your call to
make, for your own account.

## Install (three steps)

1. **Load the extension.** Open `chrome://extensions`, switch on *Developer mode* (top
   right), click *Load unpacked* and pick this folder, `extension/leboncoin/`. Pin its icon
   if you like; clicking the icon opens the options page.
2. **Create your searches.** On leboncoin.fr, go to *Immobilier → Locations*, set your
   filters (postal codes or cities, maximum rent, minimum surface, furnished or not) and sort
   by *Plus récentes*, then copy the address bar. Paste one URL per line in the options page.
   One search per area keeps every page short.
3. **Paste the Discord webhook** (the same one the Railway worker uses, or another channel),
   click *Enregistrer*, then *Tester le webhook*, then *Lancer un cycle maintenant*. The first
   cycle only records what is already on the page; alerts start with the next one.

Chrome must stay open for the extension to run; it needs no window in front, the pinned tabs
do the work. The badge shows how many alerts went out today.

## Files

| file | role |
|---|---|
| `manifest.json` | Manifest V3: alarms, storage, tabs, scripting; hosts leboncoin.fr, discord.com, raw.githubusercontent.com |
| `background.js` | service worker: the cycle (one pinned tab per search, reload, read, filter, post), badge, hourly filter refresh |
| `content.js` + `parse.js` | run in the search tab: `__NEXT_DATA__` JSON first, rendered cards as fallback, verification-page detection |
| `filter.js` | JavaScript port of `scraper/notify.py::matches()` (postal codes, area and room minimums, per-department and area-tiered rent caps) |
| `options.html` / `options.js` | settings, status per search, log, download of the last page where no ad was recognised |
| `test.js` | `node extension/leboncoin/test.js` — the same filter cases as the Python tests, plus parser and challenge-detection cases on synthetic data |

If a cycle reports *aucune annonce reconnue* although the tab shows ads, the page layout
changed: download the HTML sample from the options page so the selectors in `parse.js` and
`content.js` can be adjusted. The seen-id memory keeps the last 5 000 ids.
