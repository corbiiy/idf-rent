"""Laforêt (laforet.com) — national HTML list pages, filtered to Île-de-France by postal code.

List pages (newest first, 40 ads each):
    https://www.laforet.com/louer/location-appartement[?page=N]
    https://www.laforet.com/louer/location-maison[?page=N]
There is no region- or department-scoped list page (/louer/location-appartement/ile-de-france
is a 404) and robots.txt disallows the search endpoint (/louer/rechercher?*), so the module
walks the national lists and keeps the cards whose postal code is in IDF (~1/3 of them).

Each ad is an <article data-counter-model-value="property" data-counter-id-value="<id>"> block.
The card's "favourite" button carries the structured fields as data-gtm-item-*-param attributes
(id, type, city, zipcode, price, size, rooms-nb, criteria); the photo carousel repeats the ad
link once per photo. The list card has no DPE, no posting date and no coordinates.
The only "captcha" on the page is a reCAPTCHA site key for the contact-form widget, not a block.
"""
from __future__ import annotations

import logging
import re
from html import unescape
from typing import Iterator, Optional

from ..model import IDF_DEPARTMENTS, Listing

log = logging.getLogger(__name__)

SLUG = "laforet"
LABEL = "Laforêt"
COLOR = "#c8102e"
BASE = "https://www.laforet.com"

KINDS = ("appartement", "maison")
HOUSING_TYPES = {"appartement", "maison", "studio", "loft", "duplex", "triplex", "villa"}

_ARTICLE = re.compile(
    r'<article\b[^>]*data-counter-model-value="property"[^>]*data-counter-id-value="(\d+)"[^>]*>(.*?)</article>',
    re.S,
)
_GTM = re.compile(r'data-gtm-item-([a-z-]+)-param="([^"]*)"')
_HREF = re.compile(r'href="(https?://www\.laforet\.com/agence-immobiliere/[^"]+)"')
_IMG = re.compile(r'<img[^>]+src="(/glide/[^"]+)"')
_CRITERIA = re.compile(r'<div\s+class="text[^"]*"\s*>\s*([^<]+?)\s*</div>')
_CITY = re.compile(r'font-bold text-gray-600">\s*(.*?)\s*</span>', re.S)


def list_url(kind: str = "appartement", page: int = 1) -> str:
    url = f"{BASE}/louer/location-{kind}"
    return f"{url}?page={page}" if page > 1 else url


def _text(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(s).replace("\xa0", " ")).strip()


def _int(text: Optional[str]) -> Optional[int]:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def _float(text: Optional[str]) -> Optional[float]:
    try:
        return float((text or "").replace(",", "."))
    except ValueError:
        return None


def parse_list(html: str) -> list[Listing]:
    out = []
    for ad_id, body in _ARTICLE.findall(html):
        gtm = {k: unescape(v) for k, v in _GTM.findall(body)}
        m = _HREF.search(body)
        if not m or gtm.get("id", ad_id) != ad_id:
            continue
        url = m.group(1)
        kind = (gtm.get("type") or "").strip()
        if kind.lower() not in HOUSING_TYPES:
            continue
        photos = []
        for src in _IMG.findall(body):
            if f"/{ad_id}" in src and src not in photos:
                photos.append(BASE + unescape(src))
        criteria = [_text(c) for c in _CRITERIA.findall(body)]
        joined = " • ".join(criteria)
        bedrooms = None
        mb = re.search(r"(\d+)\s*ch(?:ambre|bre)s?\b", joined)
        if mb:
            bedrooms = int(mb.group(1))
        furnished = True if (re.search(r"\bMeublé\b", joined) or gtm.get("meuble") == "true") else None
        city_m = _CITY.search(body)
        city_text = _text(city_m.group(1)) if city_m else ""
        pc = re.search(r"\b(\d{5})\b", gtm.get("zipcode", "")) or re.search(r"\((\d{5})\)", city_text)
        postal_code = pc.group(1) if pc else None
        city = re.sub(r"\s*\(\d{5}\)", "", city_text).strip() or gtm.get("city", "").strip()
        city = city.title() if city.isupper() else city
        rooms = _int(gtm.get("rooms-nb"))
        area = _float(gtm.get("size"))
        out.append(Listing(
            id=f"{SLUG}:{ad_id}",
            source=SLUG,
            url=url,
            title=f"{kind}" + (f" {rooms} pièce{'s' if rooms > 1 else ''}" if rooms else "") + (f" {area:g} m²" if area else "") + (f" - {city}" if city else ""),
            rent=_int(gtm.get("price")),
            charges=None,
            area=area,
            rooms=rooms,
            bedrooms=bedrooms,
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


def fetch(session, departments: list[str], max_pages: int = 2) -> Iterator[Listing]:
    wanted = {d for d in departments if d in IDF_DEPARTMENTS} or set(IDF_DEPARTMENTS)
    for kind in KINDS:
        for page in range(1, max_pages + 1):
            resp = session.get(list_url(kind, page))
            if resp.status_code != 200:
                log.warning("laforet: %s returned %s", resp.url, resp.status_code)
                break
            listings = parse_list(resp.text)
            kept = [l for l in listings if l.postal_code and l.postal_code[:2] in wanted]
            log.info("laforet: %s page %d: %d ads, %d in IDF", kind, page, len(listings), len(kept))
            yield from kept
            if not listings:
                break


def is_live(session, listing: Listing) -> Optional[bool]:
    resp = session.head(listing.url)
    if resp.status_code in (404, 410):
        return False
    if resp.status_code == 200:
        return True
    if 300 <= resp.status_code < 400:
        # a canonical-slug redirect keeps the ad id; a withdrawn ad lands on a /louer list page
        location = resp.headers.get("Location", "")
        if listing.id.split(":", 1)[1] in location:
            return True
        return False if "/louer" in location else None
    return None
