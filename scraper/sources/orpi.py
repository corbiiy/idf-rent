"""Orpi (orpi.com) — agency network.

The search page is a JavaScript app, but the server still embeds the complete result
set for a department as JSON in a `data-result="…"` attribute (HTML-escaped). One GET per
department therefore returns every rental (≈50–300 items), no pagination needed:

    GET https://www.orpi.com/recherche?transactions[0]=rent&locations[0][value]=<dept slug>&sort=date-down

robots.txt (User-agent *) disallows /login*, /estate/*, *agency=*, *sujet=*, *contact=*:
the URL above carries none of those parameters (the site's own canonical search URL adds
an empty `agency=`, which we deliberately leave out).
"""
from __future__ import annotations

import html
import json
import logging
import re
from typing import Iterator, Optional

from ..model import Listing

log = logging.getLogger(__name__)

SLUG = "orpi"
LABEL = "Orpi"
COLOR = "#e30613"
MIN_INTERVAL = 1800  # one 1-2 MB page per department; every 30 min is plenty
BASE = "https://www.orpi.com"

DEPARTMENTS = {
    "75": "paris",
    "77": "seine-et-marne",
    "78": "yvelines",
    "91": "essonne",
    "92": "hauts-de-seine",
    "93": "seine-saint-denis",
    "94": "val-de-marne",
    "95": "val-d-oise",
}
HOUSING = {"appartement", "maison", "studio", "loft", "duplex"}

_RESULT_RE = re.compile(r'data-result="([^"]+)"')
_POSTAL_RE = re.compile(r"-(\d{5})-[0-9a-f]{8}-")
_BEDROOMS_RE = re.compile(r"^(\d+) chambres?$")


def list_url(dept: str) -> str:
    return f"{BASE}/recherche?transactions[0]=rent&locations[0][value]={DEPARTMENTS[dept]}&sort=date-down"


def ad_url(item: dict) -> str:
    return f"{BASE}/annonce-location-{item['slug']}/"


def parse_result(page: str) -> dict:
    m = _RESULT_RE.search(page)
    if not m:
        return {}
    return json.loads(html.unescape(m.group(1)))


def normalise(item: dict) -> Optional[Listing]:
    if item.get("transaction") != "rent" or item.get("type") not in HOUSING:
        return None
    if item.get("sold") or item.get("enabled") is False:
        return None
    tags = item.get("tags") or []
    bedrooms = None
    furnished = None
    for t in tags:
        m = _BEDROOMS_RE.match(t)
        if m:
            bedrooms = int(m.group(1))
        elif t == "Meublé":
            furnished = True
        elif t == "Non meublé":
            furnished = False
    pc = _POSTAL_RE.search(item.get("slug") or "")
    city = (item.get("city") or {}).get("name") or item.get("location")
    rooms = item.get("nbRooms")
    if rooms is None and "Studio" in tags:
        rooms = 1
    area = item.get("surface")
    kind = item["type"].capitalize()
    return Listing(
        id=f"{SLUG}:{item['reference']}",
        source=SLUG,
        url=ad_url(item),
        title=f"{kind} {rooms} pièces {area:g} m² - {city}" if rooms and area else f"{kind} - {city}",
        rent=int(round(item["price"])) if item.get("price") else None,
        charges=None,
        area=float(area) if area is not None else None,
        rooms=rooms,
        bedrooms=bedrooms,
        furnished=furnished,
        owner_type="Agence",
        dpe=None,
        postal_code=pc.group(1) if pc else None,
        city=city,
        lat=item.get("latitude"),
        lng=item.get("longitude"),
        photos=[u for u in (item.get("images") or []) if isinstance(u, str) and u.startswith("http")],
        posted_at=item.get("onMarketSince"),
    )


def parse_list(page: str) -> list[Listing]:
    out = []
    for item in parse_result(page).get("items") or []:
        l = normalise(item)
        if l is not None:
            out.append(l)
    return out


def fetch(session, departments: list[str], max_pages: int = 2) -> Iterator[Listing]:
    for dept in departments:
        if dept not in DEPARTMENTS:
            log.warning("orpi: no slug for department %s", dept)
            continue
        resp = session.get(list_url(dept))
        if resp.status_code != 200:
            log.warning("orpi: %s returned %s", resp.url, resp.status_code)
            continue
        listings = parse_list(resp.text)
        log.info("orpi: dept %s: %d housing ads (count %s)", dept, len(listings), parse_result(resp.text).get("count"))
        for l in listings:
            if l.postal_code and l.postal_code[:2] != dept:
                continue
            yield l


def is_live(session, listing: Listing) -> Optional[bool]:
    resp = session.head(listing.url)
    if resp.status_code in (404, 410):
        return False
    if resp.status_code == 200:
        return True
    if 300 <= resp.status_code < 400:
        return "/annonce-" in resp.headers.get("Location", "")
    return None
