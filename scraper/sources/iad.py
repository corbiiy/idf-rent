"""iad France (iadfrance.fr) — mandatary network, server-rendered Nuxt list pages.

List page: https://www.iadfrance.fr/annonces/<dept slug>/location[?page=N]
(30 <article> cards per page, newest first by default; a page past the end renders zero cards).
Everything we need is in the card markup: the ad link (/annonce/<type>-location-...-<city>-<m2>/r<id>),
the h2 "Appartement à Colombes (92700)", the price <p> followed by "charges comprises", the
"N pièces" / "N chambres" / "N m²" list items and the carousel <img> sources. window.__NUXT__ only
holds runtime config and the ld+json only an AggregateOffer for the page, so neither lists the ads.

The list card has no DPE, no coordinates and no posting date. Non-housing cards (parking, garage,
local commercial, bureaux ...) are skipped by the type prefix of the ad URL.

robots.txt ("User-agent: *") disallows filtered/sorted query strings (?sort=, ?priceMin= ...) and
/liste/annonces*, but not /annonces/<slug>/location or its ?page=N pagination.
"""
from __future__ import annotations

import logging
import re
from html import unescape
from html.parser import HTMLParser
from typing import Iterator, Optional

from ..model import IDF_DEPARTMENTS, Listing

log = logging.getLogger(__name__)

SLUG = "iad"
LABEL = "iad"
COLOR = "#6c2bd9"
BASE = "https://www.iadfrance.fr"

DEPT_SLUGS = {
    "75": "paris-75",
    "77": "seine-et-marne-77",
    "78": "yvelines-78",
    "91": "essonne-91",
    "92": "hauts-de-seine-92",
    "93": "seine-saint-denis-93",
    "94": "val-de-marne-94",
    "95": "val-d-oise-95",
}

HOUSING_TYPES = {"appartement", "maison", "studio", "loft", "duplex", "triplex", "villa"}
AD_PATH = re.compile(r"^/annonce/([a-z]+(?:-[a-z]+)*?)-location-[^/]*/r(\d+)$")


def list_url(dept: str, page: int = 1) -> str:
    suffix = f"?page={page}" if page > 1 else ""
    return f"{BASE}/annonces/{DEPT_SLUGS[dept]}/location{suffix}"


class _CardParser(HTMLParser):
    """Collects the fields of each <article> card."""

    def __init__(self):
        super().__init__()
        self.cards: list[dict] = []
        self._card: Optional[dict] = None
        self._text_target: Optional[str] = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "article":
            self._card = {"href": None, "title": "", "paragraphs": [], "items": [], "photos": [], "text": ""}
            return
        if self._card is None:
            return
        if tag == "a" and a.get("data-dd-action-name") == "property_card_link":
            self._card["href"] = a.get("href")
        elif tag == "h2":
            self._text_target = "title"
        elif tag == "p":
            self._card["paragraphs"].append("")
            self._text_target = "paragraph"
        elif tag == "li":
            self._card["items"].append("")
            self._text_target = "item"
        elif tag == "img" and "/property/" in a.get("src", ""):
            self._card["photos"].append(unescape(a["src"]))

    def handle_endtag(self, tag):
        if self._card is None:
            return
        if tag == "article":
            self.cards.append(self._card)
            self._card = None
            self._text_target = None
        elif tag in ("h2", "p", "li"):
            self._text_target = None

    def handle_data(self, data):
        if self._card is None:
            return
        text = unescape(data).replace("\xa0", " ").replace(" ", " ").strip()
        if not text:
            return
        self._card["text"] += text + " "
        if self._text_target == "title":
            self._card["title"] = (self._card["title"] + " " + text).strip()
        elif self._text_target == "paragraph":
            self._card["paragraphs"][-1] = (self._card["paragraphs"][-1] + " " + text).strip()
        elif self._text_target == "item":
            self._card["items"][-1] = (self._card["items"][-1] + " " + text).strip()


def _int(text: str) -> Optional[int]:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def parse_list(html: str) -> list[Listing]:
    parser = _CardParser()
    parser.feed(html)
    out = []
    for c in parser.cards:
        m = AD_PATH.match(c["href"] or "")
        if not m:
            continue
        kind, ad_id = m.group(1), m.group(2)
        if kind not in HOUSING_TYPES:
            continue
        rooms = bedrooms = None
        area = None
        for item in c["items"]:
            if re.search(r"\bpi[èe]ces?\b", item):
                rooms = _int(item)
            elif "chambre" in item:
                bedrooms = _int(item)
            elif re.search(r"\d\s*m²\s*$", item):
                area = _int(item)
        price = next((p for p in c["paragraphs"] if "€" in p), "")
        rent = _int(price.split("€")[0])
        m = re.match(r"^(.*?)\s+à\s+(.*?)\s*\((\d{5})\)\s*$", c["title"])
        type_label, city, postal_code = (m.group(1), m.group(2), m.group(3)) if m else (c["title"], None, None)
        city = city.title() if city and city.isupper() else city
        title = type_label + (f" {rooms} pièce{'s' if rooms > 1 else ''}" if rooms else "") \
            + (f" {area} m²" if area else "") + (f" - {city}" if city else "")
        out.append(Listing(
            id=f"{SLUG}:{ad_id}",
            source=SLUG,
            url=BASE + c["href"],
            title=title,
            rent=rent,
            charges=None,
            area=float(area) if area else None,
            rooms=rooms,
            bedrooms=bedrooms,
            furnished=True if re.search(r"\bmeubl", c["text"], re.I) else None,
            owner_type="Agence",
            dpe=None,
            postal_code=postal_code,
            city=city,
            lat=None,
            lng=None,
            photos=c["photos"],
            posted_at=None,
        ))
    return out


def fetch(session, departments: list[str], max_pages: int = 2) -> Iterator[Listing]:
    for dept in departments:
        if dept not in DEPT_SLUGS:
            log.warning("iad: no slug for department %s", dept)
            continue
        for page in range(1, max_pages + 1):
            url = list_url(dept, page)
            resp = session.get(url)
            if resp.status_code != 200:
                log.warning("iad: %s returned %s", url, resp.status_code)
                break
            listings = parse_list(resp.text)
            log.info("iad: dept %s page %d: %d housing ads", dept, page, len(listings))
            if not listings:
                break
            for listing in listings:
                # the department page occasionally carries a stray ad from elsewhere in France
                if listing.postal_code and listing.postal_code[:2] in IDF_DEPARTMENTS:
                    yield listing


def is_live(session, listing: Listing) -> Optional[bool]:
    resp = session.head(listing.url)
    if resp.status_code in (404, 410):
        return False
    if resp.status_code == 200:
        return True
    if 300 <= resp.status_code < 400:
        # a removed ad redirects (301) to the /annonces/location list page
        location = resp.headers.get("Location", "")
        return False if "/annonces/" in location or "/annonces" == location.rstrip("/") else None
    return None
