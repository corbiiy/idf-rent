"""Century 21 (century21.fr) — department-scoped HTML list pages.

List pages (sorted by date desc by default, 20 ads each):
    https://www.century21.fr/annonces/location-appartement/d-92_hauts_de_seine/[page-N/]
    https://www.century21.fr/annonces/location-maison/d-92_hauts_de_seine/[page-N/]
Paris has no department page (d-75_paris is a 301 to v-paris), so 75 uses the city form
/annonces/location-appartement/v-paris/. An unknown location slug answers HTTP 410.

Each ad is a <div class="c-the-property-thumbnail-with-content ..." data-uid="<id>"> block linking
to /trouver_logement/detail/<id>/. The card shows the city in capitals followed by the postal code
for Paris ("PARIS 75012") but only the department number elsewhere ("ST CLOUD 92"), the area and
room count, a type title ("Appartement T3 à louer"), the rent "par mois charges comprises", one
photo and a truncated description. No DPE, bedrooms, date or coordinates on the list card.

robots.txt: /annonces/f/ (old search form), /annonces/location*/cp-* (postal-code lists) and the
agency sub-sites /a/*/annonces/ are disallowed; the department lists and ad pages are allowed.
"""
from __future__ import annotations

import logging
import re
from html import unescape
from typing import Iterator, Optional

from ..model import Listing

log = logging.getLogger(__name__)

SLUG = "century21"
LABEL = "Century 21"
COLOR = "#beaf87"
BASE = "https://www.century21.fr"

KINDS = ("appartement", "maison")

# department code -> location slug (checked 2026-10: each answers 200)
LOCATIONS = {
    "75": "v-paris",
    "77": "d-77_seine_et_marne",
    "78": "d-78_yvelines",
    "91": "d-91_essonne",
    "92": "d-92_hauts_de_seine",
    "93": "d-93_seine_saint_denis",
    "94": "d-94_val_de_marne",
    "95": "d-95_val_d_oise",
}

SKIP_TYPES = re.compile(r"^(parking|box|garage|local|bureau|terrain|commerce|fonds|immeuble|cave|entrep)", re.I)

_CARD = re.compile(r'<div class="c-the-property-thumbnail-with-content js-the-property-thumbnail-with-content[^"]*" data-uid="(\d+)"\s*>')
_HREF = re.compile(r'href="(/trouver_logement/detail/(\d+)/)"')
_IMG = re.compile(r'<img (?:data-)?src="([^"]+)"')  # cards below the fold lazy-load via data-src
_HEADING = re.compile(r'c-text-theme-heading-4[^>]*>(.*?)<br\s*/?>(.*?)<div', re.S)
_TYPE = re.compile(r'c-text-theme-heading-3[^>]*>\s*([^<]+?)\s*<')
_PRICE = re.compile(r'c-text-theme-heading-1[^>]*>\s*([^<]+?)\s*<p[^>]*>([^<]*)</p>', re.S)
_DESC = re.compile(r'tw-truncate-safe">\s*(.*?)\s*</div>', re.S)


def list_url(dept: str, kind: str = "appartement", page: int = 1) -> str:
    url = f"{BASE}/annonces/location-{kind}/{LOCATIONS[dept]}/"
    return f"{url}page-{page}/" if page > 1 else url


def _text(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", unescape(s).replace("\xa0", " ")).strip()


def _num(text: str) -> Optional[float]:
    m = re.search(r"\d[\d\s]*(?:[.,]\d+)?", text or "")
    if not m:
        return None
    return float(m.group(0).replace(" ", "").replace(",", "."))


def parse_list(html: str) -> list[Listing]:
    out = []
    starts = list(_CARD.finditer(html))
    for i, m in enumerate(starts):
        ad_id = m.group(1)
        body = html[m.end(): starts[i + 1].start() if i + 1 < len(starts) else len(html)]
        href = _HREF.search(body)
        if not href or href.group(2) != ad_id:
            continue
        kind_m = _TYPE.search(body)
        kind = _text(kind_m.group(1)) if kind_m else ""
        if not kind or SKIP_TYPES.match(kind):
            continue
        head = _HEADING.search(body)
        place, specs = (_text(head.group(1)), _text(head.group(2))) if head else ("", "")
        pm = re.match(r"(.*?)\s+(\d{5}|\d{2})$", place)
        city, geo = (pm.group(1), pm.group(2)) if pm else (place, "")
        postal_code = geo if len(geo) == 5 else None
        area_m = re.search(r"([\d,.]+)\s*m\s*2", specs)
        rooms_m = re.search(r"(\d+)\s*pi[èe]ce", specs)
        price_m = _PRICE.search(body)
        rent = _num(price_m.group(1).replace("&euro;", "")) if price_m else None
        desc_m = _DESC.search(body)
        desc = _text(desc_m.group(1)) if desc_m else ""
        furnished = None
        if re.search(r"\bnon[ -]meubl", desc, re.I):
            furnished = False
        elif re.search(r"\bmeubl", desc, re.I) or re.search(r"\bmeubl", kind, re.I):
            furnished = True
        img = _IMG.search(body)
        photos = [BASE + unescape(img.group(1))] if img and img.group(1).startswith("/imagesBien/") else []
        city = city.title() if city.isupper() else city
        out.append(Listing(
            id=f"{SLUG}:{ad_id}",
            source=SLUG,
            url=BASE + href.group(1),
            title=f"{re.sub(r'\s+à louer$', '', kind)} - {city}".strip(" -"),
            rent=int(round(rent)) if rent is not None else None,
            charges=None,
            area=_num(area_m.group(1)) if area_m else None,
            rooms=int(rooms_m.group(1)) if rooms_m else None,
            bedrooms=None,
            furnished=furnished,
            owner_type="Agence",
            dpe=None,
            postal_code=postal_code,
            city=city or None,
            lat=None,
            lng=None,
            photos=photos,
            posted_at=None,
        ))
    return out


DETAIL_POSTAL_RE = re.compile(r'itemprop="name">[^<]*\((\d{5})\)')


def detail_postal_code(html: str) -> Optional[str]:
    """The breadcrumb of the ad page reads 'Location Appartement BOULOGNE BILLANCOURT (92100)'."""
    m = DETAIL_POSTAL_RE.search(html)
    return m.group(1) if m else None


def fetch(session, departments: list[str], max_pages: int = 2, known_ids: set[str] | None = None) -> Iterator[Listing]:
    """List pages outside Paris only show the department number, so for ads not seen before
    (not in `known_ids`) one extra GET of the ad page fills in the postal code."""
    known_ids = known_ids or set()
    for dept in departments:
        if dept not in LOCATIONS:
            log.warning("century21: no location slug for department %s", dept)
            continue
        for kind in KINDS:
            for page in range(1, max_pages + 1):
                resp = session.get(list_url(dept, kind, page))
                if resp.status_code != 200:
                    log.warning("century21: %s returned %s", resp.url, resp.status_code)
                    break
                listings = parse_list(resp.text)
                log.info("century21: dept %s %s page %d: %d ads", dept, kind, page, len(listings))
                for l in listings:
                    if l.postal_code is None and l.id not in known_ids:
                        detail = session.get(l.url)
                        if detail.status_code == 200:
                            l.postal_code = detail_postal_code(detail.text)
                    yield l
                if not listings:
                    break


def is_live(session, listing: Listing) -> Optional[bool]:
    resp = session.head(listing.url)
    if resp.status_code in (404, 410):
        return False
    if resp.status_code == 200:
        return True
    if 300 <= resp.status_code < 400:
        location = resp.headers.get("Location", "")
        # withdrawn ads go to /trouver_logement/detail_non_publie/ or back to a list page
        if "detail_non_publie" in location or "/annonces/" in location:
            return False
        return None
    return None
