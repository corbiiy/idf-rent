"""Foncia (fr.foncia.com) — agency network, Angular server-rendered list pages.

List page: https://fr.foncia.com/location/<dept slug>[/page-N]   (15 ads per server-rendered page)
Ad page:   https://fr.foncia.com/location/<city slug>/<type>/<reference>.htm

Pagination is path-based on purpose: robots.txt (2026-10) disallows every URL containing
"?", so this module never sends a query string to fr.foncia.com.

The SSR page embeds the API responses the front end would otherwise fetch from
fnc-api.prod.fonciatech.net in <script id="serverApp-state" type="application/json">
(Angular transfer state, with &q; &a; &l; &g; &s; escapes). The search response there
carries price (charges included, "/ mois CC"), surface, rooms, bedrooms, DPE letter,
postal code, photos and the publication date, so the card markup is not parsed.

Every ad is listed by a Foncia agency, so owner_type is always "Agence". Furnished is
derived from the property type (appartement vs appartement-meuble). The locality of an ad
only has a city-centre point, not the ad's own position, so lat/lng are left empty.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Iterator, Optional

from ..model import IDF_DEPARTMENTS, Listing

log = logging.getLogger(__name__)

SLUG = "foncia"
LABEL = "Foncia"
COLOR = "#0033a0"
BASE = "https://fr.foncia.com"

# department code -> Foncia locality slug (all eight answer 200 on /location/<slug>, 2026-10)
DEPARTMENTS = {
    "75": "paris-75",
    "77": "seine-et-marne-77",
    "78": "yvelines-78",
    "91": "essonne-91",
    "92": "hauts-de-seine-92",
    "93": "seine-saint-denis-93",
    "94": "val-de-marne-94",
    "95": "val-d-oise-95",
}
HOUSING_PREFIXES = ("appartement", "maison", "studio", "loft", "duplex", "villa")

_STATE_RE = re.compile(r'<script id="serverApp-state" type="application/json">(.*?)</script>', re.S)
_ESCAPES = (("&q;", '"'), ("&s;", "'"), ("&l;", "<"), ("&g;", ">"), ("&a;", "&"))


def list_url(dept: str, page: int = 1) -> str:
    suffix = f"/page-{page}" if page > 1 else ""
    return f"{BASE}/location/{DEPARTMENTS[dept]}{suffix}"


def _state(html: str) -> dict:
    m = _STATE_RE.search(html)
    if not m:
        return {}
    raw = m.group(1)
    for token, char in _ESCAPES:
        raw = raw.replace(token, char)
    try:
        return json.loads(raw)
    except ValueError:
        return {}


def _search_records(state: dict) -> list[dict]:
    for key, value in state.items():
        if "/annonces/annonces/search" in key and isinstance(value, dict):
            return (value.get("body") or {}).get("annonces") or []
    return []


def _int(value) -> Optional[int]:
    try:
        return int(round(float(value))) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def normalise(ad: dict) -> Optional[Listing]:
    kind = (ad.get("typeBien") or "").strip().lower()
    if not kind.startswith(HOUSING_PREFIXES) or (ad.get("typeAnnonce") or "").lower() != "location":
        return None
    if (ad.get("status") or "active") != "active":
        return None
    ref = str(ad.get("reference") or "").strip()
    path = ad.get("canonicalUrl") or ""
    if not ref or not path:
        return None
    loc = ad.get("localisation") or {}
    postal_code = str(loc.get("codePostal") or loc.get("codePostalRattach") or "").strip() or None
    if not postal_code or postal_code[:2] not in IDF_DEPARTMENTS:
        return None
    titles = ad.get("titles") or {}
    surface = ad.get("surface") or {}
    area = surface.get("habitable") or surface.get("totale") or surface.get("carrez")
    photos = [f"{u}/lg.jpeg" for u in ad.get("mediasCDN") or [] if isinstance(u, str) and u.startswith("http")]
    if not photos:
        photos = [u for u in ad.get("medias") or [] if isinstance(u, str) and u.startswith("http")]
    dpe = ad.get("noteConsoEnergie")
    city = (loc.get("ville") or (loc.get("locality") or {}).get("libelle") or "").strip() or None
    return Listing(
        id=f"{SLUG}:{ref}",
        source=SLUG,
        url=BASE + path,
        title=(titles.get("main") or titles.get("description") or "").strip() or f"{kind} {city or ''}".strip(),
        rent=_int(ad.get("loyer")),
        charges=_int(ad.get("loyerAnnexe")),
        area=float(area) if area else None,
        rooms=_int(ad.get("nbPiece")) or None,
        bedrooms=_int(ad.get("nbChambre")) or None,
        furnished=kind.endswith(("meuble", "meublee")),
        owner_type="Agence",
        dpe=dpe if dpe in list("ABCDEFG") else None,
        postal_code=postal_code,
        city=city,
        lat=None,
        lng=None,
        photos=photos,
        posted_at=ad.get("datePublication") or None,
    )


def parse_list(html: str) -> list[Listing]:
    out = []
    for ad in _search_records(_state(html)):
        listing = normalise(ad)
        if listing is not None:
            out.append(listing)
    return out


def fetch(session, departments: list[str], max_pages: int = 2) -> Iterator[Listing]:
    for dept in departments:
        if dept not in DEPARTMENTS:
            log.warning("foncia: no slug for department %s", dept)
            continue
        for page in range(1, max_pages + 1):
            url = list_url(dept, page)
            resp = session.get(url)
            if resp.status_code != 200:
                log.warning("foncia: %s returned %s", url, resp.status_code)
                break
            records = _search_records(_state(resp.text))
            listings = [l for l in (normalise(ad) for ad in records) if l is not None]
            log.info("foncia: dept %s page %d: %d ads (%d housing)", dept, page, len(records), len(listings))
            yield from listings
            if not records:
                break


def is_live(session, listing: Listing) -> Optional[bool]:
    resp = session.head(listing.url)
    if resp.status_code in (404, 410):
        return False
    if resp.status_code == 200:
        return True
    if 300 <= resp.status_code < 400:
        # a removed ad is sent back to the search list; a still-live ad only ever redirects to another .htm
        return None if resp.headers.get("Location", "").endswith(".htm") else False
    return None
