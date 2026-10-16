"""One crawl cycle, shared by the CLI (python -m scraper) and the long-running worker."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from . import store
from .http import PoliteSession, SourceBlocked
from .model import Listing
from .sources import SOURCES

log = logging.getLogger(__name__)


def _parse(ts: str | None) -> float:
    if not ts:
        return 0.0
    try:
        return datetime.fromisoformat(ts).timestamp()
    except ValueError:
        return 0.0


def due_sources(sources: list[str], status: dict[str, dict]) -> list[str]:
    """Sources whose MIN_INTERVAL has elapsed, least recently run first."""
    now = time.time()
    out = []
    for slug in sources:
        mod = SOURCES[slug]
        last = _parse((status.get(slug) or {}).get("last_run"))
        if now - last >= getattr(mod, "MIN_INTERVAL", 0):
            out.append(slug)
    return sorted(out, key=lambda s: _parse((status.get(s) or {}).get("last_run")))


def run_cycle(stored: list[Listing], session: PoliteSession, departments: list[str], sources: list[str],
              pages: int = 2, liveness: bool = True, hash_photos: bool = True,
              status: dict[str, dict] | None = None, budget: float | None = None,
              ) -> tuple[list[Listing], list[Listing], dict[str, dict]]:
    """Crawl the due sources, fold results into `stored`, re-check liveness, prune.

    `status` is the per-source block from the last save and is updated in place:
    {slug: {last_run, last_ok, last_error, count}}. `budget` (seconds) stops starting
    new sources once exceeded; the ones not reached go first next cycle because they
    keep the oldest last_run. Returns (stored, new listings, status)."""
    status = status if status is not None else {}
    new_total: list[Listing] = []
    started = time.monotonic()
    for slug in due_sources(sources, status):
        if budget is not None and time.monotonic() - started > budget:
            log.info("budget exhausted; %s and later sources wait for the next cycle", slug)
            break
        mod = SOURCES[slug]
        st = status.setdefault(slug, {})
        st["last_run"] = store.now_iso()
        fresh: list[Listing] = []
        try:
            for l in mod.fetch(session, departments, max_pages=pages):
                fresh.append(l)
            st["last_ok"] = st["last_run"]
            st["last_error"] = None
        except SourceBlocked as exc:
            log.warning("%s: blocked, stopping this source: %s", slug, exc)
            st["last_error"] = f"blocked: {exc}"[:300]
        except Exception as exc:
            log.exception("%s: failed: %s", slug, exc)
            st["last_error"] = f"{exc.__class__.__name__}: {exc}"[:300]
        new = store.merge(stored, fresh, session, hash_photos=hash_photos)
        stored = list({l.id: l for l in stored + new}.values())
        st["count"] = sum(1 for l in stored if l.source == slug and not l.expired)
        log.info("%s: %d fetched, %d new%s", slug, len(fresh), len(new), f" ({st['last_error']})" if st.get("last_error") else "")
        new_total.extend(new)
    if liveness:
        expired = store.liveness(stored, session)
        log.info("liveness: %d marked expired", expired)
    return store.prune(stored), new_total, status
