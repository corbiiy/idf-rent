"""Duplicate detection: by URL, by (rent, area, postal_code, first-photo hash), and by
(rent, area, postal_code, rounded lat/lng) for the same agency ad syndicated to several sites."""
from __future__ import annotations

import hashlib
import io
import logging
from typing import Optional

from .model import Listing

log = logging.getLogger(__name__)


def photo_hash(session, url: str) -> Optional[str]:
    """Perceptual dHash (64 bit) of an image, so recompressed copies on another
    site still match. Falls back to a SHA-1 of the bytes if Pillow is missing."""
    try:
        resp = session.get_asset(url)
    except Exception as exc:  # the photo CDN is not the source; never stop a run over it
        log.debug("photo fetch failed for %s: %s", url, exc)
        return None
    if resp.status_code != 200 or not resp.content:
        return None
    try:
        from PIL import Image
    except ImportError:
        return "sha1:" + hashlib.sha1(resp.content).hexdigest()
    try:
        img = Image.open(io.BytesIO(resp.content)).convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    except Exception:
        return "sha1:" + hashlib.sha1(resp.content).hexdigest()
    px = list(img.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            left, right = px[row * 9 + col], px[row * 9 + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"dhash:{bits:016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def fingerprint(listing: Listing) -> Optional[tuple]:
    if listing.rent is None or listing.area is None or not listing.postal_code:
        return None
    return (listing.rent, int(listing.area), listing.postal_code)


def same_photo(h1: Optional[str], h2: Optional[str], max_distance: int = 6) -> bool:
    if not h1 or not h2:
        return False
    if h1.startswith("dhash:") and h2.startswith("dhash:"):
        return hamming(h1[6:], h2[6:]) <= max_distance
    return h1 == h2


def geo_key(listing: Listing) -> Optional[tuple]:
    """(rent, area, postal_code, lat, lng) rounded to ~100 m; None when the ad has no coordinates."""
    fp = fingerprint(listing)
    if fp is None or listing.lat is None or listing.lng is None:
        return None
    return fp + (round(listing.lat, 3), round(listing.lng, 3))


def find_duplicate(listing: Listing, existing: list[Listing]) -> Optional[Listing]:
    """Return the stored listing that `listing` duplicates, if any."""
    for other in existing:
        if other.url == listing.url:
            return other
    fp = fingerprint(listing)
    if fp is None:
        return None
    gk = geo_key(listing)
    for other in existing:
        if other.id == listing.id or fingerprint(other) != fp:
            continue
        if same_photo(listing.photo_hash, other.photo_hash):
            return other
        if gk is not None and geo_key(other) == gk:
            return other
    return None
