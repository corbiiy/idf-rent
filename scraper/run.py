"""One crawl cycle, shared by the CLI (python -m scraper) and the long-running worker."""
from __future__ import annotations

import logging

from . import store
from .http import PoliteSession, SourceBlocked
from .model import Listing
from .sources import SOURCES

log = logging.getLogger(__name__)


def run_cycle(stored: list[Listing], session: PoliteSession, departments: list[str], sources: list[str],
              pages: int = 2, liveness: bool = True, hash_photos: bool = True) -> tuple[list[Listing], list[Listing], dict[str, str]]:
    """Crawl every source, fold results into `stored`, re-check liveness, prune.
    Returns (stored, new listings, per-source status). Does not save."""
    new_total: list[Listing] = []
    status: dict[str, str] = {}
    for slug in sources:
        mod = SOURCES[slug]
        fresh: list[Listing] = []
        try:
            for l in mod.fetch(session, departments, max_pages=pages):
                fresh.append(l)
            status[slug] = f"ok ({len(fresh)} ads)"
        except SourceBlocked as exc:
            log.warning("%s: blocked, stopping this source: %s", slug, exc)
            status[slug] = f"blocked ({exc})"
        except Exception as exc:
            log.exception("%s: failed: %s", slug, exc)
            status[slug] = f"error ({exc})"
        new = store.merge(stored, fresh, session, hash_photos=hash_photos)
        stored = list({l.id: l for l in stored + new}.values())
        log.info("%s: %d fetched, %d new", slug, len(fresh), len(new))
        new_total.extend(new)
    if liveness:
        expired = store.liveness(stored, session)
        log.info("liveness: %d marked expired", expired)
    return store.prune(stored), new_total, status
