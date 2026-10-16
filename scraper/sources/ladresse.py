"""L'Adresse (ladresse.com) — agency network, HTML list pages.

List page: https://www.ladresse.com/recherche/location/<appartement|maison>/<dept slug>[/<page>]?tri=date-desc
(40 cards per page, path-based pagination, newest first). Cards are <a class="bien" data-id="...">
blocks; a Leaflet script further down the page carries one L.marker([lat, lng]) per card, tied to the
ad by its '<span id="annonce-<id>">' popup, which gives coordinates.

The list card has no DPE and no posting date. Rent is "charges comprises" ("/ mois cc").

robots.txt: the "User-agent: *" group allows everything but /admin/, /_sauv/, /conf/, /page/, /2013/;
the many "Disallow: /" lines belong to a block of named scraper user agents, not to ours.
"""
from __future__ import annotations

import logging
import re
from html import unescape
from html.parser import HTMLParser
from typing import Iterator, Optional

from ..model import Listing

log = logging.getLogger(__name__)

SLUG = "ladresse"
LABEL = "L'Adresse"
COLOR = "#f28c00"
BASE = "https://www.ladresse.com"
PAGE_SIZE = 40
KINDS = ("appartement", "maison")

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


def list_url(dept: str, kind: str = "appartement", page: int = 1) -> str:
    suffix = f"/{page}" if page > 1 else ""
    return f"{BASE}/recherche/location/{kind}/{DEPT_SLUGS[dept]}{suffix}?tri=date-desc"


class _CardParser(HTMLParser):
    """Collects the fields of each <a class="bien" data-id> card."""

    def __init__(self):
        super().__init__()
        self.cards: list[dict] = []
        self._card: Optional[dict] = None
        self._text_target: Optional[str] = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "").split()
        if tag == "a" and "bien" in cls and a.get("data-id"):
            self._card = {"id": a["data-id"], "href": a.get("href", ""), "photos": [],
                          "geo": "", "price": "", "type": "", "description": ""}
            return
        if self._card is None:
            return
        if tag == "img" and a.get("src", "").startswith("http"):
            self._card["photos"].append(a["src"])
        elif tag == "span" and "bien-geo" in cls:
            self._text_target = "geo"
        elif tag == "div" and "bien-prix" in cls:
            self._text_target = "price"
        elif tag == "div" and "bien-type" in cls:
            self._text_target = "type"
        elif tag == "div" and "bien-description" in cls:
            self._text_target = "description"
        elif tag == "br" and self._text_target == "description":
            self._card["description"] += " | "

    def handle_endtag(self, tag):
        if self._card is None:
            return
        if tag == "a":
            self.cards.append(self._card)
            self._card = None
            self._text_target = None
        elif tag == "div" and self._text_target in ("price", "type", "description"):
            # nested spans inside these divs keep the target; the div's own end tag closes it
            self._text_target = None
        elif tag == "span" and self._text_target == "geo":
            self._text_target = None

    def handle_data(self, data):
        if self._card is None or not self._text_target:
            return
        text = unescape(data).replace("\xa0", " ").strip()
        if text:
            self._card[self._text_target] = (self._card[self._text_target] + " " + text).strip()


def _int(text: str) -> Optional[int]:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def _coords(html: str) -> dict[str, tuple[float, float]]:
    """Map of ad id -> (lat, lng) from the Leaflet markers script."""
    out = {}
    for lat, lng, ad_id in re.findall(r"L\.marker\(\[\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*\][^;]*?id=\"annonce-(\d+)\"", html):
        out[ad_id] = (float(lat), float(lng))
    return out


def parse_list(html: str) -> list[Listing]:
    parser = _CardParser()
    parser.feed(html)
    coords = _coords(html)
    out = []
    for c in parser.cards:
        kind = c["type"].strip().lower()
        if kind and not re.search(r"appartement|maison|studio|loft|duplex|villa|propri", kind):
            continue
        desc = c["description"]
        m = re.search(r"(\d+)\s*pi[èe]ce", desc)
        rooms = int(m.group(1)) if m else None
        m = re.search(r"(\d+)\s*chambre", desc)
        bedrooms = int(m.group(1)) if m else None
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*m²", desc)
        area = float(m.group(1).replace(",", ".")) if m else None
        m = re.search(r"-(\d{5})/\d+/?$", c["href"])
        postal_code = m.group(1) if m else None
        city = re.sub(r"\s*\(\d+\)\s*$", "", c["geo"]).strip() or None
        if city and re.match(r"^Paris \d{2}$", city):  # "Paris 07 (75)": the arrondissement is in postal_code
            city = "Paris"
        rent_text = c["price"].split("€")[0]
        rent = _int(rent_text)
        lat, lng = coords.get(c["id"], (None, None))
        type_label = c["type"].strip() or "Logement"
        title = type_label + (f" {rooms} pièce{'s' if rooms and rooms > 1 else ''}" if rooms else "") \
            + (f" {area:g} m²" if area else "") + (f" - {city}" if city else "")
        out.append(Listing(
            id=f"{SLUG}:{c['id']}",
            source=SLUG,
            url=BASE + c["href"].split("?")[0],
            title=title,
            rent=rent,
            charges=None,
            area=area,
            rooms=rooms,
            bedrooms=bedrooms,
            furnished=True if re.search(r"\bmeubl", desc, re.I) else None,
            owner_type="Agence",
            dpe=None,
            postal_code=postal_code,
            city=city,
            lat=lat,
            lng=lng,
            photos=c["photos"],
            posted_at=None,
        ))
    return out


def fetch(session, departments: list[str], max_pages: int = 2) -> Iterator[Listing]:
    for dept in departments:
        if dept not in DEPT_SLUGS:
            log.warning("ladresse: no slug for department %s", dept)
            continue
        for kind in KINDS:
            for page in range(1, max_pages + 1):
                url = list_url(dept, kind, page)
                resp = session.get(url)
                if resp.status_code != 200:
                    log.warning("ladresse: %s returned %s", url, resp.status_code)
                    break
                listings = parse_list(resp.text)
                log.info("ladresse: dept %s %s page %d: %d ads", dept, kind, page, len(listings))
                yield from listings
                if len(listings) < PAGE_SIZE:
                    break


def is_live(session, listing: Listing) -> Optional[bool]:
    resp = session.head(listing.url)
    if resp.status_code in (404, 410):
        return False
    if resp.status_code == 200:
        return True
    if 300 <= resp.status_code < 400:
        location = resp.headers.get("Location", "")
        return False if "/recherche/" in location or location.rstrip("/") in ("", BASE) else None
    return None
