"""python -m scraper [--departments 75,92] [--sources pap,bienici] [--pages N] [--no-liveness] [--notify]"""
from __future__ import annotations

import argparse
import logging
import sys

from .http import PoliteSession
from .model import IDF_DEPARTMENTS
from .sources import SOURCES
from . import store
from .notify import notify_new
from .run import run_cycle


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m scraper", description="Crawl new IDF rentals into data/listings.json")
    p.add_argument("--departments", default=",".join(IDF_DEPARTMENTS), help="comma list of department codes (default: all 8 IDF)")
    p.add_argument("--sources", default=",".join(SOURCES), help="comma list of source slugs (default: all)")
    p.add_argument("--pages", type=int, default=2, help="max list pages per department and source")
    p.add_argument("--no-liveness", action="store_true", help="skip re-checking stored links")
    p.add_argument("--no-photo-hash", action="store_true", help="skip downloading first photos for dedupe")
    p.add_argument("--notify", action="store_true", help="post new listings matching filter.json to the Discord webhook")
    p.add_argument("--notify-test", action="store_true", help="post the 3 most recent stored listings matching filter.json, to check the webhook")
    p.add_argument("--force", action="store_true", help="ignore each source's MIN_INTERVAL (crawl PAP even if tried today)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("scraper")

    departments = [d.strip() for d in args.departments.split(",") if d.strip()]
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    unknown = [s for s in sources if s not in SOURCES]
    if unknown:
        p.error(f"unknown sources: {unknown}; known: {list(SOURCES)}")

    session = PoliteSession()
    stored = store.load()
    log.info("store: %d listings (%d expired)", len(stored), sum(l.expired for l in stored))

    status = {} if args.force else store.load_status()
    stored, new_total, status = run_cycle(stored, session, departments, sources, pages=args.pages,
                                          liveness=not args.no_liveness, hash_photos=not args.no_photo_hash,
                                          status=status)
    store.save(stored, status=status)
    log.info("saved %d listings to %s", len(stored), store.DATA_FILE)

    labels = {s: m.LABEL for s, m in SOURCES.items()}
    if args.notify_test:
        notify_new(stored, labels, test=True)
    elif args.notify:
        notify_new(new_total, labels)

    for slug in sources:
        st = status.get(slug) or {}
        print(f"{slug}: {'error ' + st['last_error'] if st.get('last_error') else 'ok'} (count {st.get('count', 0)})")
    print(f"new: {len(new_total)}, total: {len(stored)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
