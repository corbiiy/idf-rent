"""Pure parsing of a leboncoin search results page into Listing objects.

Two inputs are supported, in order of preference:

1. The `__NEXT_DATA__` JSON the Next.js page embeds. Ads are dicts with at least
   `list_id` and `subject`; they are found by walking the JSON, so the exact path
   (`props.pageProps.searchData.ads` today) does not matter.
2. Rendered cards, as a list of dicts the watcher extracts in-page with a few
   data-qa-id selectors (see leboncoin_watch.CARD_SCRIPT).

Nothing here talks to the network, so it is unit-tested against synthetic fixtures.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterator, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper.model import Listing  # noqa: E402

SLUG = "leboncoin"
LABEL = "leboncoin"
BASE = "https://www.leboncoin.fr"

_NEXT_RE = re.compile(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
HOUSING = {"appartement", "maison", "studio", "loft", "duplex", "1", "2"}  # real_estate_type labels or codes


def next_data(html: str) -> Optional[dict]:
    m = _NEXT_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def _walk_ads(node) -> Iterator[dict]:
    """Yield every dict that looks like a leboncoin ad, wherever it sits in the JSON."""
    if isinstance(node, dict):
        if "list_id" in node and "subject" in node:
            yield node
            return
        for v in node.values():
            yield from _walk_ads(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_ads(v)


def _attrs(ad: dict) -> dict[str, dict]:
    return {a.get("key"): a for a in ad.get("attributes") or [] if isinstance(a, dict) and a.get("key")}


def _int(v) -> Optional[int]:
    try:
        return int(float(str(v).replace(",", ".").replace(" ", "")))
    except (TypeError, ValueError):
        return None


def _float(v) -> Optional[float]:
    try:
        return float(str(v).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return None


def ad_to_listing(ad: dict) -> Optional[Listing]:
    attrs = _attrs(ad)
    kind = (attrs.get("real_estate_type") or {})
    kind_label = str(kind.get("value_label") or kind.get("value") or "").lower()
    if kind_label and kind_label not in HOUSING:
        return None  # parking, terrain, bureau...
    price = ad.get("price")
    if isinstance(price, list):
        price = price[0] if price else None
    rent = _int(price)
    loc = ad.get("location") or {}
    images = ad.get("images") or {}
    photos = [u for u in (images.get("urls_large") or images.get("urls") or []) if isinstance(u, str)]
    if not photos and images.get("thumb_url"):
        photos = [images["thumb_url"]]
    furnished_raw = str((attrs.get("furnished") or {}).get("value_label") or (attrs.get("furnished") or {}).get("value") or "").lower()
    furnished = True if furnished_raw in ("meublé", "meuble", "1") else False if furnished_raw in ("non meublé", "non meuble", "2") else None
    dpe = str((attrs.get("energy_rate") or {}).get("value") or "").upper()
    owner = (ad.get("owner") or {}).get("type")
    url = ad.get("url") or f"{BASE}/ad/locations/{ad.get('list_id')}"
    if url.startswith("/"):
        url = BASE + url
    rooms = _int((attrs.get("rooms") or {}).get("value"))
    bedrooms = _int((attrs.get("bedrooms") or {}).get("value"))
    return Listing(
        id=f"{SLUG}:{ad.get('list_id')}",
        source=SLUG,
        url=url,
        title=(ad.get("subject") or "").strip(),
        rent=rent,
        charges=None,
        area=_float((attrs.get("square") or {}).get("value")),
        rooms=rooms,
        bedrooms=bedrooms,
        furnished=furnished,
        owner_type={"private": "Particulier", "pro": "Agence"}.get(owner),
        dpe=dpe if dpe in list("ABCDEFG") else None,
        postal_code=str(loc.get("zipcode") or "") or None,
        city=loc.get("city"),
        lat=loc.get("lat"),
        lng=loc.get("lng"),
        photos=photos,
        posted_at=ad.get("first_publication_date") or ad.get("index_date"),
    )


def parse_next_data(html: str) -> list[Listing]:
    data = next_data(html)
    if data is None:
        return []
    out = []
    seen = set()
    for ad in _walk_ads(data):
        l = ad_to_listing(ad)
        if l is not None and l.id not in seen:
            seen.add(l.id)
            out.append(l)
    return out


_M2_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*m²")
_ROOMS_RE = re.compile(r"(\d+)\s*pi[èe]ce")
_PLACE_RE = re.compile(r"^(.*?)\s*(\d{5})\s*$")
_ID_RE = re.compile(r"/(\d{6,})(?:[/?#].*)?$")


def card_to_listing(card: dict) -> Optional[Listing]:
    """`card` is what CARD_SCRIPT extracts: {href, title, price, details, place, img}."""
    href = card.get("href") or ""
    m = _ID_RE.search(href)
    if not m:
        return None
    details = card.get("details") or ""
    area = _M2_RE.search(details)
    rooms = _ROOMS_RE.search(details)
    place = _PLACE_RE.match((card.get("place") or "").strip())
    return Listing(
        id=f"{SLUG}:{m.group(1)}",
        source=SLUG,
        url=href if href.startswith("http") else BASE + href,
        title=(card.get("title") or "").strip(),
        rent=_int(re.sub(r"[^\d]", "", card.get("price") or "")) if re.search(r"\d", card.get("price") or "") else None,
        charges=None,
        area=_float(area.group(1)) if area else None,
        rooms=int(rooms.group(1)) if rooms else None,
        bedrooms=None,
        furnished=True if "meublé" in details.lower() and "non meublé" not in details.lower() else None,
        owner_type=None,
        dpe=None,
        postal_code=place.group(2) if place else None,
        city=place.group(1).strip() or None if place else (card.get("place") or None),
        lat=None,
        lng=None,
        photos=[card["img"]] if card.get("img") else [],
        posted_at=None,
    )


def parse_cards(cards: list[dict]) -> list[Listing]:
    out, seen = [], set()
    for c in cards:
        l = card_to_listing(c)
        if l is not None and l.id not in seen:
            seen.add(l.id)
            out.append(l)
    return out


CHALLENGE_MARKERS = ("captcha-delivery.com", "geo.captcha-delivery", "datadome", "Vérification", "Please enable JS", "blocked")


def looks_like_challenge(html: str, url: str = "") -> bool:
    low = html.lower()
    if "captcha-delivery" in low or "datadome" in low[:50000] or "/captcha" in url:
        return True
    return len(html) < 5000 and "<script" in low and "__next_data__" not in low and "aditem" not in low
