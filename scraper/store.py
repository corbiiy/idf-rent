"""data/listings.json: load, merge new crawl results, liveness pass, save."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .dedupe import find_duplicate, photo_hash
from .http import PoliteSession, SourceBlocked
from .model import Listing
from .sources import SOURCES

log = logging.getLogger(__name__)

DATA_FILE = Path(os.environ.get("IDF_RENT_DATA") or Path(__file__).resolve().parent.parent / "data" / "listings.json")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load(path: Path = DATA_FILE) -> list[Listing]:
    return [Listing.from_dict(d) for d in _read(path).get("listings", [])]


def load_status(path: Path = DATA_FILE) -> dict[str, dict]:
    """Per-source crawl status as saved last time: {slug: {last_run, last_ok, last_error, count}}."""
    out = {}
    for slug, info in _read(path).get("sources", {}).items():
        out[slug] = {k: info.get(k) for k in ("last_run", "last_ok", "last_error", "count")}
    return out


def save(listings: list[Listing], path: Path = DATA_FILE, status: dict[str, dict] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    listings = sorted(listings, key=lambda l: l.first_seen or "", reverse=True)
    status = status or {}
    counts: dict[str, int] = {}
    for l in listings:
        if not l.expired:
            counts[l.source] = counts.get(l.source, 0) + 1
    sources = {}
    for slug, m in SOURCES.items():
        st = status.get(slug, {})
        sources[slug] = {
            "label": m.LABEL,
            "color": getattr(m, "COLOR", "#6b665d"),
            "count": counts.get(slug, 0),
            "last_run": st.get("last_run"),
            "last_ok": st.get("last_ok"),
            "last_error": st.get("last_error"),
        }
    payload = {
        "generated_at": now_iso(),
        "count": len(listings),
        "sources": sources,
        "listings": [l.to_dict() for l in listings],
    }
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    tmp.replace(path)


def merge(stored: list[Listing], fresh: list[Listing], session: PoliteSession, hash_photos: bool = True, max_hashes: int = 150) -> list[Listing]:
    """Fold a crawl into the store. Returns the listings that are new (not seen before).
    At most `max_hashes` first photos are downloaded per call to keep a run short."""
    by_id = {l.id: l for l in stored}
    ts = now_iso()
    new: list[Listing] = []
    hashes = 0
    for l in fresh:
        if l.id in by_id:
            cur = by_id[l.id]
            cur.last_seen = ts
            cur.expired = False
            # refresh mutable fields (price drops, more photos) but keep timestamps
            for f in ("rent", "charges", "area", "rooms", "bedrooms", "furnished", "dpe", "photos", "title", "lat", "lng"):
                v = getattr(l, f)
                if v not in (None, [], ""):
                    setattr(cur, f, v)
            if hash_photos and cur.photos and not cur.photo_hash and hashes < max_hashes:
                hashes += 1
                cur.photo_hash = photo_hash(session, cur.photos[0])
            continue
        if hash_photos and l.photos and not l.photo_hash and hashes < max_hashes:
            hashes += 1
            l.photo_hash = photo_hash(session, l.photos[0])
        dup = find_duplicate(l, list(by_id.values()))
        if dup is not None:
            log.info("duplicate: %s == %s", l.id, dup.id)
            dup.last_seen = ts
            dup.expired = False
            continue
        l.first_seen = l.last_seen = ts
        by_id[l.id] = l
        new.append(l)
    return new


def liveness(stored: list[Listing], session: PoliteSession, max_checks: int = 60, min_age_hours: float = 6.0) -> int:
    """Re-check stored links that have not been seen in a crawl recently.
    Marks 404/410 (or 'off the market') as expired. Returns the number expired."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=min_age_hours)).isoformat()
    candidates = [l for l in stored if not l.expired and (l.last_seen or "") < cutoff]
    candidates.sort(key=lambda l: l.last_seen or "")
    expired = 0
    blocked: set[str] = set()
    for l in candidates[:max_checks]:
        if l.source in blocked:
            continue
        mod = SOURCES.get(l.source)
        if mod is None:
            continue
        try:
            live = mod.is_live(session, l)
        except SourceBlocked as exc:
            log.warning("liveness: %s", exc)
            blocked.add(l.source)
            continue
        except Exception as exc:
            log.warning("liveness: %s: %s", l.url, exc)
            continue
        if live is False:
            l.expired = True
            expired += 1
        elif live is True:
            l.last_seen = now_iso()
    return expired


def prune(stored: list[Listing], keep_expired_days: int = 14) -> list[Listing]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_expired_days)).isoformat()
    return [l for l in stored if not (l.expired and (l.last_seen or "") < cutoff)]
