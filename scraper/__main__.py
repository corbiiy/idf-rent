"""python -m scraper [--departments 75,92] [--sources pap,bienici] [--pages N] [--no-liveness] [--notify]"""
from __future__ import annotations

import argparse
import logging
import sys

from .http import PoliteSession, SourceBlocked
from .model import IDF_DEPARTMENTS
from .sources import SOURCES
from . import store
from .notify import notify_new


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m scraper", description="Crawl new IDF rentals into data/listings.json")
    p.add_argument("--departments", default=",".join(IDF_DEPARTMENTS), help="comma list of department codes (default: all 8 IDF)")
    p.add_argument("--sources", default=",".join(SOURCES), help="comma list of source slugs (default: all)")
    p.add_argument("--pages", type=int, default=2, help="max list pages per department and source")
    p.add_argument("--no-liveness", action="store_true", help="skip re-checking stored links")
    p.add_argument("--no-photo-hash", action="store_true", help="skip downloading first photos for dedupe")
    p.add_argument("--notify", action="store_true", help="post new listings matching filter.json to the Discord webhook")
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

    new_total = []
    status = {}
    for slug in sources:
        mod = SOURCES[slug]
        fresh = []
        try:
            for l in mod.fetch(session, departments, max_pages=args.pages):
                fresh.append(l)
            status[slug] = f"ok ({len(fresh)} ads)"
        except SourceBlocked as exc:
            log.warning("%s: blocked, stopping this source: %s", slug, exc)
            status[slug] = f"blocked ({exc})"
        except Exception as exc:
            log.exception("%s: failed: %s", slug, exc)
            status[slug] = f"error ({exc})"
        new = store.merge(stored, fresh, session, hash_photos=not args.no_photo_hash)
        stored = list({l.id: l for l in stored + new}.values())
        log.info("%s: %d fetched, %d new", slug, len(fresh), len(new))
        new_total.extend(new)

    if not args.no_liveness:
        expired = store.liveness(stored, session)
        log.info("liveness: %d marked expired", expired)
    stored = store.prune(stored)
    store.save(stored)
    log.info("saved %d listings to %s", len(stored), store.DATA_FILE)

    if args.notify:
        notify_new(new_total, {s: m.LABEL for s, m in SOURCES.items()})

    for slug, st in status.items():
        print(f"{slug}: {st}")
    print(f"new: {len(new_total)}, total: {len(stored)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
