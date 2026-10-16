"""LocService (locservice.fr) — private-owner rentals, HTML department list pages.

Every ad is posted by a private owner ("de particulier à particulier"), so owner_type is
always "Particulier".

List page: https://www.locservice.fr/<dept slug>/location-<dept name>.html
           (Paris is the exception: https://www.locservice.fr/paris-75/location.html)
Pagination: .../location-<dept name>-p2.html (Paris: .../location-p2.html), 47 ads a page.
Requesting /<dept slug>/location.html 301-redirects to the named page for every department
but Paris, so the named URLs are used directly.

Cards are <li class="accommodation-ad"> blocks: title ("Appartement T3 meublé à louer"),
link, one photo, "<city> (<postal code>)", area, rent charges included ("2 400 € / mois")
and the first lines of the description. The list card carries no DPE, no date and no
coordinates. The page's application/ld+json only describes the list (AggregateOffer),
not the ads. Rooms ("chambre" ads) are skipped: only housing is yielded.
"""
from __future__ import annotations

import logging
import re
from html import unescape
from typing import Iterator, Optional

from ..model import IDF_DEPARTMENTS, Listing

log = logging.getLogger(__name__)

SLUG = "locservice"
LABEL = "LocService"
COLOR = "#1f9d55"
BASE = "https://www.locservice.fr"
PAGE_SIZE = 47

# department code -> (url slug, list page name); verified 2026-10 by following
# /<slug>/location.html, which 301-redirects to /<slug>/location-<name>.html
DEPARTMENTS = {
    "75": ("paris-75", ""),
    "77": ("seine-et-marne-77", "seine-et-marne"),
    "78": ("yvelines-78", "yvelines"),
    "91": ("essonne-91", "essonne"),
    "92": ("hauts-de-seine-92", "hauts-de-seine"),
    "93": ("seine-saint-denis-93", "seine-saint-denis"),
    "94": ("val-de-marne-94", "val-de-marne"),
    "95": ("val-d-oise-95", "val-d-oise"),
}

HOUSING = {"appartement", "studio", "maison", "loft", "duplex"}

_CARD_SPLIT = re.compile(r'<li class="accommodation-ad"')
_ID = re.compile(r'data-accommodation-id="(\d+)"')
_TITLE = re.compile(r'<a href="([^"]+)"[^>]*class="[^"]*stretched-link[^"]*"[^>]*>(.*?)</a>', re.S)
_KIND = re.compile(r"/location-([a-z]+)-")
_GEO = re.compile(r'name="geo"></ls-icon>\s*(.*?)\s*</li>', re.S)
_AREA = re.compile(r'name="bounding-box-circles"></ls-icon>\s*(\d+(?:[.,]\d+)?)\s*m²')
_PRICE = re.compile(r'name="wallet2"></ls-icon>\s*([\d\s \xa0]+)€')
_PHOTO = re.compile(r'<img src="(https://img\.locservice\.fr/[^"]+)"')
_DESC = re.compile(r'<p class="accommodation-ad-description">(.*?)</p>', re.S)
_ROOMS_LINE = re.compile(r"(\d+)\s*pièces?(?:\s+(\d+)\s*chambres?)?")


def list_url(dept: str, page: int = 1) -> str:
    slug, name = DEPARTMENTS[dept]
    stem = f"location-{name}" if name else "location"
    suffix = f"-p{page}" if page > 1 else ""
    return f"{BASE}/{slug}/{stem}{suffix}.html"


def _int(text: Optional[str]) -> Optional[int]:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text).replace("\xa0", " ")).strip()


def parse_list(html: str) -> list[Listing]:
    out = []
    for block in _CARD_SPLIT.split(html)[1:]:
        m_id, m_title = _ID.search(block), _TITLE.search(block)
        if not m_id or not m_title:
            continue
        url, title = m_title.group(1), _clean(m_title.group(2))
        if not url.startswith("http"):
            url = BASE + url
        kind = _KIND.search(url)
        if not kind or kind.group(1) not in HOUSING:
            continue
        geo = _GEO.search(block)
        place = _clean(geo.group(1)) if geo else ""
        pc = re.search(r"\((\d{5})\)", place)
        postal_code = pc.group(1) if pc else None
        city = re.sub(r"\s*\(\d{5}\)", "", place).strip() or None
        m_area, m_price, m_photo, m_desc = _AREA.search(block), _PRICE.search(block), _PHOTO.search(block), _DESC.search(block)
        description = _clean(m_desc.group(1)) if m_desc else ""

        rooms = bedrooms = None
        t = re.search(r"\bT(\d+)\b", title)
        if t:
            rooms = int(t.group(1))
        elif kind.group(1) == "studio":
            rooms = 1
        # LocService prefixes the description with "<city>\n<n> pièces  <n> chambres  <area> m²" when the owner filled it in
        line = _ROOMS_LINE.search(description[:120])
        if line:
            rooms = rooms or int(line.group(1))
            if line.group(2):
                bedrooms = int(line.group(2))

        out.append(Listing(
            id=f"{SLUG}:{m_id.group(1)}",
            source=SLUG,
            url=url,
            title=f"{title.replace(' à louer', '')} - {city}" if city else title,
            rent=_int(m_price.group(1)) if m_price else None,
            charges=None,
            area=float(m_area.group(1).replace(",", ".")) if m_area else None,
            rooms=rooms,
            bedrooms=bedrooms,
            furnished="meublé" in title.lower(),  # the title is generated from the ad's furnished flag
            owner_type="Particulier",
            dpe=None,
            postal_code=postal_code,
            city=city,
            lat=None,
            lng=None,
            photos=[m_photo.group(1)] if m_photo else [],
            posted_at=None,
        ))
    return out


def fetch(session, departments: list[str], max_pages: int = 2) -> Iterator[Listing]:
    for dept in departments:
        if dept not in DEPARTMENTS:
            log.warning("locservice: no list page for department %s", dept)
            continue
        for page in range(1, max_pages + 1):
            resp = session.get(list_url(dept, page))
            if resp.status_code != 200:
                log.warning("locservice: %s returned %s", resp.url, resp.status_code)
                break
            listings = parse_list(resp.text)
            cards = len(_CARD_SPLIT.findall(resp.text))
            log.info("locservice: dept %s page %d: %d cards, %d housing ads", dept, page, cards, len(listings))
            for l in listings:
                if l.postal_code and l.postal_code[:2] not in IDF_DEPARTMENTS:
                    continue
                yield l
            if cards < PAGE_SIZE:
                break


def is_live(session, listing: Listing) -> Optional[bool]:
    resp = session.head(listing.url)
    if resp.status_code in (404, 410):
        return False
    if resp.status_code == 200:
        return True
    if 300 <= resp.status_code < 400:
        # a deleted ad 301-redirects to the city list page (…/location-appartement-paris-15.html)
        location = resp.headers.get("Location", "")
        return False if location.endswith(".html") else None
    return None
