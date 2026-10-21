#!/usr/bin/env python3
"""Local leboncoin watcher: re-opens your own saved searches in your own browser
session every few minutes and posts new ads to Discord.

This is deliberately NOT a scraper:
- it runs on your Mac, in a visible Chromium with a persistent profile where you logged
  in by hand once (~/Library/Application Support/idf-rent/leboncoin-profile);
- it opens each search like you would, at a human cadence (default every 5 minutes,
  never under 3), with a pause between searches;
- it sends nothing but the normal page requests: no proxy, no user-agent or fingerprint
  change, no headless tricks, no captcha solving. If leboncoin shows a verification
  page, the cycle stops, you get one Discord message, and you solve it yourself in the
  watcher window;
- leboncoin ads stay on this machine (seen ids + a local JSON archive). They are never
  pushed to the GitHub repository or the public site: leboncoin's listings database is
  protected and republishing it is what got aggregators condemned.

Usage:
  python3 local/leboncoin_watch.py --login            open the window, log in, press Enter
  python3 local/leboncoin_watch.py --once --dry-run   one cycle, print instead of Discord
  python3 local/leboncoin_watch.py                    run forever (launchd does this)

Config: local/leboncoin_searches.json (list of search URLs), local/.env (DISCORD_WEBHOOK_URL,
optional LBC_INTERVAL seconds), filter.json at the repo root (same alert filter as the
other sources: postal codes, per-department rent cap, area_min, room_min).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

import leboncoin_parse as lp  # noqa: E402
from scraper.model import Listing  # noqa: E402
from scraper.notify import notify_new, send_discord  # noqa: E402

log = logging.getLogger("leboncoin")

APP_DIR = Path.home() / "Library" / "Application Support" / "idf-rent"
PROFILE_DIR = APP_DIR / "leboncoin-profile"
SEEN_FILE = APP_DIR / "leboncoin-seen.json"
ARCHIVE_FILE = APP_DIR / "leboncoin-listings.json"
DEBUG_DIR = APP_DIR / "debug"
SEARCHES_FILE = HERE / "leboncoin_searches.json"
ENV_FILE = HERE / ".env"

MIN_INTERVAL = 180
DEFAULT_INTERVAL = 300
CHALLENGE_NOTICE_EVERY = 3600  # seconds between two "please verify" Discord messages

# Fallback when the page carries no __NEXT_DATA__: read the rendered cards.
CARD_SCRIPT = """
() => [...document.querySelectorAll('a[data-qa-id="aditem_container"], a[href*="/ad/"]')].map(a => {
  const q = (sel) => { const e = a.querySelector(sel); return e ? e.innerText.trim() : ""; };
  const img = a.querySelector("img");
  return {
    href: a.getAttribute("href") || "",
    title: q('[data-qa-id="aditem_title"]') || (a.getAttribute("title") || "") || q("h2, h3, p"),
    price: q('[data-qa-id="aditem_price"]') || q('[data-test-id="price"]'),
    details: [...a.querySelectorAll("p, span")].map(e => e.innerText.trim()).filter(t => /m²|pièce|meubl/i.test(t)).join(" · "),
    place: [...a.querySelectorAll("p, span")].map(e => e.innerText.trim()).find(t => /\\b\\d{5}\\b/.test(t)) || "",
    img: img ? (img.currentSrc || img.src || "") : ""
  };
})
"""


def load_env(path: Path = ENV_FILE) -> None:
    """KEY=VALUE lines; values already in the environment win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_searches(path: Path = SEARCHES_FILE) -> list[str]:
    if not path.exists():
        raise SystemExit(f"{path} is missing: copy leboncoin_searches.example.json and put your own search URLs in it")
    data = json.loads(path.read_text(encoding="utf-8"))
    urls = [s["url"] if isinstance(s, dict) else s for s in data]
    urls = [u for u in urls if isinstance(u, str) and u.startswith("https://www.leboncoin.fr/")]
    if not urls:
        raise SystemExit("no leboncoin.fr search URL found in leboncoin_searches.json")
    return urls


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_search(page, url: str) -> tuple[str, list[Listing]]:
    """Open one search URL in the existing session. Returns ("ok"|"challenge"|"empty", listings)."""
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    try:
        page.wait_for_selector('#__NEXT_DATA__, [data-qa-id="aditem_container"]', timeout=15_000)
    except Exception:
        pass
    time.sleep(2 + random.random() * 2)
    html = page.content()
    if lp.looks_like_challenge(html, page.url):
        return "challenge", []
    listings = lp.parse_next_data(html)
    if not listings:
        try:
            cards = page.evaluate(CARD_SCRIPT)
        except Exception as exc:
            log.warning("card extraction failed: %s", exc)
            cards = []
        listings = lp.parse_cards(cards)
    if not listings:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        dump = DEBUG_DIR / f"leboncoin-{datetime.now().strftime('%Y%m%d-%H%M%S')}.html"
        dump.write_text(html, encoding="utf-8")
        log.warning("no ads parsed on %s; page saved to %s for inspection", url, dump)
        return "empty", []
    return "ok", listings


def run_cycle(context, urls: list[str], seen: dict, archive: dict, dry_run: bool, first_run: bool, state: dict) -> int:
    page = context.pages[0] if context.pages else context.new_page()
    new: list[Listing] = []
    for i, url in enumerate(urls):
        if i:
            time.sleep(5 + random.random() * 5)  # a person does not open two searches in the same second
        try:
            status, listings = read_search(page, url)
        except Exception as exc:
            log.warning("could not open %s: %s", url, exc)
            continue
        if status == "challenge":
            log.warning("leboncoin asks for a verification; stopping this cycle (solve it in the watcher window)")
            last = state.get("last_challenge_notice", 0)
            if time.time() - last > CHALLENGE_NOTICE_EVERY:
                state["last_challenge_notice"] = time.time()
                hook = os.environ.get("DISCORD_WEBHOOK_URL")
                if hook and not dry_run:
                    send_discord([{"title": "leboncoin asks for verification", "description": "Open the watcher window and solve it; the watcher resumes on its next cycle."}], hook)
                else:
                    print("[notice] leboncoin asks for verification, open the watcher window and solve it")
            break
        log.info("%s: %d ads on the page", url[:80], len(listings))
        for l in listings:
            if l.id in seen:
                continue
            seen[l.id] = now_iso()
            l.first_seen = l.last_seen = seen[l.id]
            archive[l.id] = l.to_dict()
            new.append(l)
    if first_run:
        log.info("first run: %d ads recorded as already seen, no alert sent", len(new))
        return 0
    if not new:
        return 0
    if dry_run:
        os.environ.pop("DISCORD_WEBHOOK_URL", None)  # notify_new then prints the matches
    return notify_new(new, {lp.SLUG: lp.LABEL})


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--login", action="store_true", help="open the browser so you can log in, then exit")
    p.add_argument("--once", action="store_true", help="run a single cycle and exit")
    p.add_argument("--dry-run", action="store_true", help="print matches instead of posting to Discord")
    p.add_argument("--interval", type=int, default=None, help=f"seconds between cycles (default {DEFAULT_INTERVAL}, minimum {MIN_INTERVAL})")
    p.add_argument("--notify-first-run", action="store_true", help="alert on everything found in the first cycle (default: just record it)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    load_env()
    interval = args.interval or int(os.environ.get("LBC_INTERVAL", DEFAULT_INTERVAL))
    if interval < MIN_INTERVAL:
        log.warning("interval %ss is below the %ss floor; using %ss", interval, MIN_INTERVAL, MIN_INTERVAL)
        interval = MIN_INTERVAL

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("playwright is not installed: python3 -m pip install --user playwright && python3 -m playwright install chromium")

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=False, locale="fr-FR", viewport={"width": 1280, "height": 900},
            args=["--window-size=1280,900"],
        )
        try:
            if args.login:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://www.leboncoin.fr/", wait_until="domcontentloaded")
                print("Log in to leboncoin in the window (accept or refuse cookies as you like), then press Enter here.")
                input()
                return 0

            urls = load_searches()
            seen = load_json(SEEN_FILE, {})
            archive = load_json(ARCHIVE_FILE, {})
            state: dict = {}
            first_run = not seen and not args.notify_first_run  # nothing seen yet: record, do not alert
            while True:
                started = time.monotonic()
                try:
                    sent = run_cycle(context, urls, seen, archive, args.dry_run, first_run, state)
                    log.info("cycle done: %d seen in total, %d alerts", len(seen), sent)
                except Exception as exc:
                    log.exception("cycle failed: %s", exc)
                save_json(SEEN_FILE, seen)
                save_json(ARCHIVE_FILE, archive)
                first_run = not seen and not args.notify_first_run
                if args.once:
                    return 0
                wait = max(MIN_INTERVAL, interval - (time.monotonic() - started))
                wait *= 0.9 + random.random() * 0.2  # a little jitter, like a human
                log.info("next cycle in %ds", int(wait))
                time.sleep(wait)
        finally:
            context.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
