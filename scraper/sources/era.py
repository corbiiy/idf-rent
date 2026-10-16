"""ERA Immobilier (eraimmobilier.com) — agency network, Angular server-rendered list pages.

List page: https://www.eraimmobilier.com/location-<appartement|maison>/ile-de-france-1/<dept slug>-<geo id>[?page=N]
10 ads per page. The SSR page embeds the JSON the front end would otherwise fetch from
api.eraimmobilier.com in <script id="ng-state" type="application/json"> (Angular transfer
state); the search response (with price, area, rooms, DPE, coordinates, photos and the
publication date) is read from there rather than from the <app-annonce-card> markup.

robots.txt (2026-10) disallows /louer and /acheter but allows /location-appartement
and /location-maison, and ?page= is not a blocked query parameter.

Every ad is listed by an ERA agency, so owner_type is always "Agence". The list record
has no charges field (the price shown is charges included) and no furnished flag; the
latter is inferred from the title/description wording.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Iterator, Optional

from ..model import IDF_DEPARTMENTS, Listing

log = logging.getLogger(__name__)

SLUG = "era"
LABEL = "ERA"
COLOR = "#e2001a"
BASE = "https://www.eraimmobilier.com"
REGION = "ile-de-france-1"

# department code -> (url slug, ERA geo_departement_id), from /api/v2/geoloc/regions/1
DEPARTMENTS = {
    "75": ("paris", 80),
    "77": ("seine-et-marne", 82),
    "78": ("yvelines", 83),
    "91": ("essonne", 96),
    "92": ("hauts-de-seine", 97),
    "93": ("seine-saint-denis", 98),
    "94": ("val-de-marne", 99),
    "95": ("val-doise", 100),
}
KINDS = ("appartement", "maison")
HOUSING = {"appartement", "maison", "studio", "loft", "duplex", "villa"}

_STATE_RE = re.compile(r'<script id="ng-state" type="application/json">(.*?)</script>', re.S)


def list_url(dept: str, page: int = 1, kind: str = "appartement") -> str:
    slug, geo = DEPARTMENTS[dept]
    suffix = f"?page={page}" if page > 1 else ""
    return f"{BASE}/location-{kind}/{REGION}/{slug}-{geo}{suffix}"


def _state(html: str) -> dict:
    m = _STATE_RE.search(html)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except ValueError:
        return {}


def _search_records(state: dict) -> list[dict]:
    for key, value in state.items():
        if "/api/v2/annonces/search?" in key and isinstance(value, dict):
            return value.get("data") or []
    return []


def _furnished(text: str) -> Optional[bool]:
    if re.search(r"\bnon[ -]meubl", text, re.I):
        return False
    if re.search(r"\bmeubl", text, re.I):
        return True
    if re.search(r"\b(location|loué|louée|appartement|studio|maison|logement)\s+vide\b", text, re.I):
        return False
    return None


def _float(value) -> Optional[float]:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _int(value) -> Optional[int]:
    try:
        return int(round(float(value))) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def normalise(ad: dict) -> Optional[Listing]:
    kind = (ad.get("type_bien") or "").strip().lower()
    if kind not in HOUSING or (ad.get("type_annonce") or "").lower() != "location":
        return None
    postal_code = str(ad.get("code_postal") or "").strip() or None
    if not postal_code or postal_code[:2] not in IDF_DEPARTMENTS:
        return None
    geo = ad.get("geoloc") or {}
    images = ad.get("images") or {}
    photos = [u for u in (images.get("big") or ad.get("photo") or []) if isinstance(u, str) and u.startswith("http")]
    geo_ville = ad.get("geo_ville") or {}
    city = (geo_ville.get("nom") or ad.get("ville") or "").strip() or None
    text = f"{ad.get('libelle') or ''}\n{ad.get('descriptif') or ''}"
    dpe = ad.get("bilan_dpe")
    return Listing(
        id=f"{SLUG}:{ad['id']}",
        source=SLUG,
        url=f"{BASE}/annonces/{ad['id']}",
        title=(ad.get("libelle") or "").strip() or f"{ad.get('type_bien')} {city or ''}".strip(),
        rent=_int(ad.get("prix")),
        charges=None,
        area=_float(ad.get("surface_habitable")) or None,
        rooms=_int(ad.get("nb_pieces")) or None,
        bedrooms=_int(ad.get("nb_chambres")) or None,
        furnished=_furnished(text),
        owner_type="Agence",
        dpe=dpe if dpe in list("ABCDEFG") else None,
        postal_code=postal_code,
        city=city,
        lat=_float(geo.get("lat")),
        lng=_float(geo.get("lng")),
        photos=photos,
        posted_at=ad.get("date_publication") or None,
    )


def parse_list(html: str) -> list[Listing]:
    out = []
    for ad in _search_records(_state(html)):
        if not ad.get("id"):
            continue
        listing = normalise(ad)
        if listing is not None:
            out.append(listing)
    return out


def fetch(session, departments: list[str], max_pages: int = 2) -> Iterator[Listing]:
    for dept in departments:
        if dept not in DEPARTMENTS:
            log.warning("era: no geo id for department %s", dept)
            continue
        for kind in KINDS:
            for page in range(1, max_pages + 1):
                url = list_url(dept, page, kind)
                resp = session.get(url)
                if resp.status_code != 200:
                    log.warning("era: %s returned %s", url, resp.status_code)
                    break
                records = _search_records(_state(resp.text))
                listings = [l for l in (normalise(ad) for ad in records if ad.get("id")) if l is not None]
                log.info("era: dept %s %s page %d: %d ads", dept, kind, page, len(listings))
                yield from listings
                if not records:
                    break


def is_live(session, listing: Listing) -> Optional[bool]:
    # The ad route always answers 200 (single-page app); a removed ad just has no ad record
    # in the embedded state, so the body has to be read.
    resp = session.get(listing.url)
    if resp.status_code in (404, 410):
        return False
    if 300 <= resp.status_code < 400:
        return False if "/annonces/" not in resp.headers.get("Location", "") else None
    if resp.status_code != 200:
        return None
    state = _state(resp.text)
    if not state:
        return None
    ad_id = listing.id.split(":", 1)[1]
    return any(key.endswith(f"/api/v2/annonces/{ad_id}") for key in state)
