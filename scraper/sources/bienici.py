"""Bien'ici — public JSON search endpoint used by its own web front end.

GET https://www.bienici.com/realEstateAds.json?filters=<json>
GET https://www.bienici.com/realEstateAd.json?id=<id>      (liveness)

robots.txt only restricts HTML search URLs (/recherche/*), not these JSON paths.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Iterator, Optional

from ..model import Listing

log = logging.getLogger(__name__)

SLUG = "bienici"
LABEL = "Bien'ici"
COLOR = "#0f4c81"
BASE = "https://www.bienici.com"
PAGE_SIZE = 100

# department code -> Bien'ici zoneId (from https://res.bienici.com/suggest.json?q=<name>)
ZONE_IDS = {
    "75": "-71525",
    "77": "-7383",
    "78": "-7457",
    "91": "-7401",
    "92": "-7449",
    "93": "-7389",
    "94": "-7458",
    "95": "-7433",
}

PROPERTY_TYPES = {"flat": "appartement", "house": "maison", "loft": "loft", "townhouse": "maison"}
OWNER_TYPES = {"agency": "Agence", "mandatary": "Agence", "network": "Agence", "individual": "Particulier"}


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def ad_url(ad: dict) -> str:
    kind = PROPERTY_TYPES.get(ad.get("propertyType"), "appartement")
    rooms = ad.get("roomsQuantity") or 1
    rooms_part = f"{rooms}pieces" if rooms > 1 else "1piece"
    return f"{BASE}/annonce/location/{_slug(ad.get('city') or 'x')}/{kind}/{rooms_part}/{ad['id']}"


def _dpe(value) -> Optional[str]:
    return value if value in list("ABCDEFG") else None


def normalise(ad: dict) -> Listing:
    pos = (ad.get("blurInfo") or {}).get("position") or {}
    photos = [p.get("url_photo") for p in ad.get("photos") or [] if p.get("url_photo")]
    rent = ad.get("price")
    return Listing(
        id=f"{SLUG}:{ad['id']}",
        source=SLUG,
        url=ad_url(ad),
        title=(ad.get("title") or "").strip() or f"{PROPERTY_TYPES.get(ad.get('propertyType'), 'Bien')} {ad.get('city', '')}".strip(),
        rent=int(rent) if rent is not None else None,
        charges=int(ad["charges"]) if ad.get("charges") is not None else None,
        area=ad.get("surfaceArea"),
        rooms=ad.get("roomsQuantity"),
        bedrooms=ad.get("bedroomsQuantity"),
        furnished=ad.get("isFurnished"),
        owner_type=OWNER_TYPES.get(ad.get("accountType"), "Agence" if ad.get("adCreatedByPro") else None),
        dpe=_dpe(ad.get("energyClassification")),
        postal_code=ad.get("postalCode"),
        city=ad.get("city"),
        lat=pos.get("lat"),
        lng=pos.get("lon"),
        photos=photos,
        posted_at=ad.get("publicationDate"),
    )


def fetch(session, departments: list[str], max_pages: int = 3) -> Iterator[Listing]:
    for dept in departments:
        zone = ZONE_IDS.get(dept)
        if not zone:
            log.warning("bienici: no zone id for department %s", dept)
            continue
        for page in range(1, max_pages + 1):
            filters = {
                "size": PAGE_SIZE,
                "from": (page - 1) * PAGE_SIZE,
                "page": page,
                "filterType": "rent",
                "propertyType": ["flat", "house", "loft", "townhouse"],
                "sortBy": "publicationDate",
                "sortOrder": "desc",
                "onTheMarket": [True],
                "zoneIdsByTypes": {"zoneIds": [zone]},
            }
            resp = session.get(f"{BASE}/realEstateAds.json", params={"filters": json.dumps(filters)})
            resp.raise_for_status()
            data = resp.json()
            ads = data.get("realEstateAds") or []
            log.info("bienici: dept %s page %d: %d ads (total %s)", dept, page, len(ads), data.get("total"))
            for ad in ads:
                if ad.get("adType") != "rent":
                    continue
                yield normalise(ad)
            if len(ads) < PAGE_SIZE:
                break


def is_live(session, listing: Listing) -> Optional[bool]:
    ad_id = listing.id.split(":", 1)[1]
    resp = session.get(f"{BASE}/realEstateAd.json", params={"id": ad_id})
    if resp.status_code in (404, 410):
        return False
    if resp.ok:
        try:
            status = resp.json().get("status") or {}
        except ValueError:
            return None
        return bool(status.get("onTheMarket", True))
    return None
