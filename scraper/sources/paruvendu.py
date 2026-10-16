"""Paruvendu (paruvendu.fr) — mixed private owners and agencies, HTML search pages.

List page: https://www.paruvendu.fr/immobilier/recherche/location/<appartement|maison>/<dept slug>/
Pagination: ?p=2, 30 ads a page (the crawl stops when the "Suivant" link is missing). The site also has a region page (.../ile-de-france/) but the
department pages exist for all 8 IDF departments, so the `departments` argument is honoured.

Cards are <div class="blocAnnonce"> blocks, parsed with regexes over each block: id (data-id),
link (/immobilier/location/<kind>/<id>), rent "950 € CC*" (charges included), a title block
"Appartement / 35 m² / Paris 10" or "Nanterre (92)", tags (pièces, chambres), a DPE badge,
the first lines of the description, a "Particulier" badge or the agency logo, and the
"dernière mise à jour" date. The card gives a postal code only for Paris (arrondissement);
other cities come with their department number only, so postal_code is None for them.
The page's application/ld+json only describes the list (AggregateOffer), not the ads.

robots.txt allows these search pages and the ad pages; the legacy /immobilier/annonceimmofo/
and ?pagv= URLs are disallowed and never requested.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from html import unescape
from typing import Iterator, Optional

from ..model import IDF_DEPARTMENTS, Listing

log = logging.getLogger(__name__)

SLUG = "paruvendu"
LABEL = "Paruvendu"
COLOR = "#e4002b"
BASE = "https://www.paruvendu.fr"
PAGE_SIZE = 30
KINDS = ("appartement", "maison")

# department code -> url slug (from the department links on the Île-de-France search page)
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

HOUSING = {"appartement", "maison", "studio", "loft", "duplex", "villa"}

_CARD_SPLIT = re.compile(r'<div\b[^>]*\bclass="blocAnnonce')
_NEXT = re.compile(r'class="pgsuiv"><a href="[^"]*\?p=(\d+)"')
_ID = re.compile(r'data-id="(\d+)"')
_LINK = re.compile(r'href="(/immobilier/location/([a-z-]+)/(\d+[A-Z0-9]*))"')
_TITLE = re.compile(r"<h3[^>]*>\s*<a[^>]*>\s*<span>\s*(.*?)\s*</span>", re.S)
_PRICE = re.compile(r"<!-- Prix -->\s*<div>\s*([\d\s \xa0]+)&euro;(.*?)</div>", re.S)
_TAG = re.compile(r'<(?:li|span) class="text-xs text-grey-600[^"]*">\s*(.*?)\s*</(?:li|span)>', re.S)
_DPE = re.compile(r"NoteEnerg_([A-G])\b")
_DESC = re.compile(r'<p class="text-sm text-justify[^"]*">\s*(.*?)\s*</p>', re.S)
_PSEUDO = re.compile(r'class="pseudoinfo">\s*(.*?)\s*</span>', re.S)
_DATE = re.compile(r"Date dernière mise à jour.*?/>\s*(\d\d)/(\d\d)/(\d{4})", re.S)
_PHOTO = re.compile(r"""(?:src\s*=\s*|imageElement\.src = )['"](https://img\.paruvendu\.fr/media_ext/[^'"]+)['"]""")


def list_url(dept: str, kind: str = "appartement", page: int = 1) -> str:
    url = f"{BASE}/immobilier/recherche/location/{kind}/{DEPARTMENTS[dept]}/"
    return f"{url}?p={page}" if page > 1 else url


def _int(text: Optional[str]) -> Optional[int]:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def _area(text: str) -> Optional[float]:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*m²", text)
    return float(m.group(1).replace(",", ".")) if m else None


def _clean(text: str) -> str:
    text = re.sub(r"<sup>\s*2\s*</sup>", "²", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", unescape(text).replace("\xa0", " ")).strip()


def _place(text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """'Paris 10' -> (Paris 10, 75010, 75); 'Nanterre (92)' -> (Nanterre, None, 92)."""
    m = re.match(r"Paris\s+(\d{1,2})\b", text)
    if m:
        return f"Paris {int(m.group(1))}", f"750{int(m.group(1)):02d}", "75"
    m = re.match(r"(.*?)\s*\((\d{2,3})\)\s*$", text)
    if m:
        return m.group(1).strip() or None, None, m.group(2)
    return text or None, None, None


def parse_list(html: str) -> list[Listing]:
    out = []
    for block in _CARD_SPLIT.split(html)[1:]:
        m_id, m_link = _ID.search(block), _LINK.search(block)
        if not m_id or not m_link:
            continue
        path, kind, ad_id = m_link.groups()
        if kind not in HOUSING:
            continue
        title = _TITLE.search(block)
        lines = [_clean(x) for x in title.group(1).split("\n")] if title else []
        lines = [x for x in lines if x]
        kind_label = lines[0] if lines else kind.capitalize()
        area = next((_area(x) for x in lines if "m²" in x), None)
        city, postal_code, dept = _place(lines[-1]) if len(lines) > 1 else (None, None, None)
        if dept and dept not in IDF_DEPARTMENTS:
            continue

        rooms = bedrooms = None
        for tag in (_clean(t) for t in _TAG.findall(block)):
            if re.search(r"\d+\s*pièce", tag):
                rooms = _int(tag)
            elif re.search(r"\d+\s*chambre", tag):
                bedrooms = _int(tag)
        m_price, m_dpe, m_desc, m_date = _PRICE.search(block), _DPE.search(block), _DESC.search(block), _DATE.search(block)
        description = _clean(m_desc.group(1)) if m_desc else ""
        furnished: Optional[bool] = None
        if re.search(r"\bnon[\s-]+meublé", description, re.I):
            furnished = False
        elif re.search(r"\bmeublé", description, re.I):  # accented: "meuble" alone is furniture
            furnished = True

        pseudo = _PSEUDO.search(block)
        if pseudo and "particulier" in pseudo.group(1).lower():
            owner_type: Optional[str] = "Particulier"
        elif 'alt="pro :' in block or "imgOffice" in block:
            owner_type = "Agence"
        else:
            owner_type = None

        photos = []
        for p in _PHOTO.findall(block):
            if p not in photos:
                photos.append(p)
        posted_at = f"{m_date.group(3)}-{m_date.group(2)}-{m_date.group(1)}" if m_date else None
        try:
            if posted_at:
                date.fromisoformat(posted_at)
        except ValueError:
            posted_at = None

        out.append(Listing(
            id=f"{SLUG}:{ad_id}",
            source=SLUG,
            url=BASE + path,
            title=" ".join(x for x in (kind_label, f"{rooms} pièce{'s' if rooms > 1 else ''}" if rooms else None, f"{area:g} m²" if area else None) if x) + (f" - {city}" if city else ""),
            rent=_int(m_price.group(1)) if m_price else None,
            charges=None,
            area=area,
            rooms=rooms,
            bedrooms=bedrooms,
            furnished=furnished,
            owner_type=owner_type,
            dpe=m_dpe.group(1) if m_dpe else None,
            postal_code=postal_code,
            city=city,
            lat=None,
            lng=None,
            photos=photos,
            posted_at=posted_at,
        ))
    return out


DETAIL_POSTAL_RES = (
    re.compile(r"setTargeting\('CP',\s*\['(\d{5})'\]"),                # ad-targeting block, present on every ad page
    re.compile(r'"CP"\s*:\s*"(\d{5})"'),
    re.compile(r'"name"\s*:\s*"[^"]*\((\d{5})\)"'),                     # breadcrumb 'Boulogne-Billancourt (92100)', when present
)


def detail_postal_code(html: str) -> Optional[str]:
    for rx in DETAIL_POSTAL_RES:
        m = rx.search(html)
        if m:
            return m.group(1)
    return None


def fetch(session, departments: list[str], max_pages: int = 2, known_ids: set[str] | None = None) -> Iterator[Listing]:
    """Cards outside Paris show only the department ("Nanterre (92)"), so ads never seen
    before (not in `known_ids`) cost one extra GET of the ad page to get the postal code."""
    known_ids = known_ids or set()
    for dept in departments:
        if dept not in DEPARTMENTS:
            log.warning("paruvendu: no list page for department %s", dept)
            continue
        for kind in KINDS:
            for page in range(1, max_pages + 1):
                resp = session.get(list_url(dept, kind, page))
                if resp.status_code != 200:
                    log.warning("paruvendu: %s returned %s", resp.url, resp.status_code)
                    break
                listings = parse_list(resp.text)
                cards = len(_CARD_SPLIT.findall(resp.text))
                log.info("paruvendu: dept %s %s page %d: %d cards, %d housing ads", dept, kind, page, cards, len(listings))
                for l in listings:
                    if l.postal_code is None and l.id not in known_ids:
                        detail = session.get(l.url)
                        if detail.status_code == 200:
                            l.postal_code = detail_postal_code(detail.text)
                    yield l
                if not cards or not _NEXT.search(resp.text):
                    break


def is_live(session, listing: Listing) -> Optional[bool]:
    resp = session.head(listing.url)
    if resp.status_code in (404, 410):
        return False
    if resp.status_code == 200:
        return True
    if 300 <= resp.status_code < 400:
        location = resp.headers.get("Location", "")
        return False if "/recherche/" in location else None
    return None
