"""Lodgis (lodgis.com) — furnished rentals in Paris, HTML category pages.

Lodgis is a single agency renting furnished flats in Paris, so owner_type is always
"Agence" and furnished is always True. Only department 75 applies: when "75" is not in
`departments` the source yields nothing.

Hub:      https://www.lodgis.com/fr/paris,location-meublee/
          links to one category page per arrondissement, discovered at run time:
Category: https://www.lodgis.com/fr/paris,location-meublee/location-meuble-paris-<arr>_<id>.cat.html[?p=<page>]
          (`<link rel="next">` carries the next page; ~50 cards per page)
Ad:       https://www.lodgis.com/fr/paris,location-meublee/appartement/LPA<id>-<slug>.mod.html

Cards are <div class="card card__appart"> blocks: price "/mois" (charges included) or
"/semaine" for short stays (skipped; a promo card shows the old price then the current one), title "Studio meublé" / "Appartement meublé N chambres",
surface, quarter and arrondissement. No posting date, DPE or coordinates on the list page.

robots.txt disallows /ajax*, /impression/ and query strings with add=, del=, surf=, cur=;
the plain category pages and their ?p= pagination are allowed.
"""
from __future__ import annotations

import logging
import re
from html import unescape
from html.parser import HTMLParser
from typing import Iterator, Optional
from urllib.parse import urljoin

from ..model import Listing

log = logging.getLogger(__name__)

SLUG = "lodgis"
LABEL = "Lodgis"
COLOR = "#2a7f62"
MIN_INTERVAL = 3600  # 20 arrondissement pages of ~0.9 MB per pass; stock changes slowly
BASE = "https://www.lodgis.com"
HUB_URL = f"{BASE}/fr/paris,location-meublee/"

_CATEGORY_RE = re.compile(r"/fr/paris,location-meublee/location-meuble-paris-(\d{1,2})_(\d+)\.cat\.html$")
_AD_ID_RE = re.compile(r"/([A-Z]{2,4}\d+)-[^/]*\.mod\.html$")


def list_url(category_url: str, page: int = 1) -> str:
    """Page `page` of a category page (the ?p= form used by the site's own pagination)."""
    return category_url if page <= 1 else f"{category_url}?p={page}"


def category_urls(hub_html: str) -> list[tuple[str, str]]:
    """(arrondissement, absolute category url) for every Paris arrondissement linked from the hub."""
    found: dict[str, str] = {}
    for href in re.findall(r'href="([^"]*location-meuble-paris-\d{1,2}_\d+\.cat\.html)"', hub_html):
        url = urljoin(HUB_URL, unescape(href))
        m = _CATEGORY_RE.search(url)
        if m:
            found.setdefault(m.group(1), url)
    return sorted(found.items(), key=lambda kv: int(kv[0]))


class _CardParser(HTMLParser):
    """Collects the fields of each card__appart block, plus the rel=next link."""

    def __init__(self):
        super().__init__()
        self.cards: list[dict] = []
        self.next_url: Optional[str] = None
        self._card: Optional[dict] = None
        self._depth = 0
        self._text_target: Optional[str] = None
        self._price_done = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        classes = cls.split()
        if tag == "link" and a.get("rel") == "next" and a.get("href"):
            self.next_url = a["href"]
            return
        if tag == "div" and "card__appart" in classes:
            self._card = {"photos": [], "prices": [], "price_unit": "", "title": "", "surface": "", "area_name": "", "arr": ""}
            self._depth = 1
            self._price_done = False
            return
        if self._card is None:
            return
        if tag == "div":
            self._depth += 1
            if "card-surface" in classes:
                self._text_target = "surface"
        elif tag == "a" and a.get("href") and "href" not in self._card and ".mod.html" in a["href"]:
            self._card["href"] = unescape(a["href"])
        elif tag == "img" and "card-img-top" in classes:
            src = a.get("src") or a.get("data-src") or ""  # lazy-loaded cards carry data-src only
            if src.startswith("http"):
                self._card["photos"].append(unescape(src))
        elif tag == "p" and "card__appart__title" in classes:
            self._text_target = "title"
        elif tag == "p" and "card-text" in classes and "small" in classes:
            self._text_target = "area_name"
        elif tag == "p" and "card-text" in classes and not self._price_done:
            self._text_target = "price_unit"
        elif tag == "span" and "price" in classes and self._text_target == "price_unit":
            self._card["prices"].append("")  # a promo card lists the old price then the current one
            self._text_target = "price"
        elif tag == "span" and "small" in classes:
            self._text_target = "arr"

    def handle_endtag(self, tag):
        if self._card is None:
            return
        if tag == "div":
            self._depth -= 1
            if self._depth == 0:
                self.cards.append(self._card)
                self._card = None
                return
            if self._text_target == "surface":
                self._text_target = None
        elif tag == "span":
            if self._text_target == "price":
                self._text_target = "price_unit"
            elif self._text_target == "arr":
                self._text_target = None
        elif tag == "p":
            if self._text_target == "price_unit":
                self._price_done = True
            self._text_target = None

    def handle_data(self, data):
        if self._card is None or not self._text_target:
            return
        text = unescape(data).replace("\xa0", " ").strip()
        if not text:
            return
        if self._text_target == "price":
            self._card["prices"][-1] = (self._card["prices"][-1] + " " + text).strip()
        else:
            self._card[self._text_target] = (self._card[self._text_target] + " " + text).strip()


def _int(text: str) -> Optional[int]:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def parse_list(html: str, arrondissement: Optional[str] = None) -> tuple[list[Listing], Optional[str]]:
    """Listings of one category page and the absolute url of the next page (None on the last)."""
    parser = _CardParser()
    parser.feed(html)
    out = []
    for c in parser.cards:
        href = c.get("href")
        if not href:
            continue
        url = urljoin(HUB_URL, href)
        m = _AD_ID_RE.search(url)
        if not m:
            continue
        if "/mois" not in c["price_unit"]:
            continue  # weekly / nightly short-stay price: not a monthly rent
        rent = _int(c["prices"][-1]) if c["prices"] else None  # last = current (promo) price
        if not rent:
            continue
        title = c["title"]
        bm = re.search(r"(\d+)\s*chambre", title)
        if bm:
            bedrooms = int(bm.group(1))
            rooms = bedrooms + 1
        elif re.search(r"\bstudio\b", title, re.I):  # "Studio meublé", "Duplex meublé studio"
            bedrooms, rooms = 0, 1
        else:
            bedrooms = rooms = None
        am = re.search(r"Paris\s*(\d{1,2})\s*°", c["arr"]) or (arrondissement and re.match(r"(\d{1,2})$", arrondissement))
        postal_code = f"750{int(am.group(1)):02d}" if am else None
        quarter = c["area_name"]
        out.append(Listing(
            id=f"{SLUG}:{m.group(1)}",
            source=SLUG,
            url=url,
            title=title + (f" {c['surface']}" if c["surface"] else "") + (f" - {quarter}" if quarter else "") + (f" - Paris {int(am.group(1))}e" if am else ""),
            rent=rent,
            charges=None,
            area=_int(c["surface"]),
            rooms=rooms,
            bedrooms=bedrooms,
            furnished=True,
            owner_type="Agence",
            dpe=None,
            postal_code=postal_code,
            city="Paris",
            lat=None,
            lng=None,
            photos=c["photos"],
            posted_at=None,
        ))
    next_url = urljoin(HUB_URL, unescape(parser.next_url)) if parser.next_url else None
    return out, next_url


def _get(session, url: str):
    """session.get, following one same-site redirect (the session does not follow them)."""
    resp = session.get(url)
    if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("Location"):
        resp = session.get(urljoin(url, resp.headers["Location"]))
    return resp


def fetch(session, departments: list[str], max_pages: int = 2) -> Iterator[Listing]:
    if "75" not in departments:
        log.info("lodgis: Paris only; department 75 not requested")
        return
    hub = _get(session, HUB_URL)
    if hub.status_code != 200:
        log.warning("lodgis: hub %s returned %s", HUB_URL, hub.status_code)
        return
    categories = category_urls(hub.text)
    if not categories:
        log.warning("lodgis: no arrondissement category links found on the hub page")
        return
    for arr, cat_url in categories:
        url: Optional[str] = cat_url
        for page in range(1, max_pages + 1):
            if not url:
                break
            resp = _get(session, url)
            if resp.status_code != 200:
                log.warning("lodgis: %s returned %s", url, resp.status_code)
                break
            listings, url = parse_list(resp.text, arr)
            log.info("lodgis: Paris %s page %d: %d ads", arr, page, len(listings))
            yield from listings
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
        return None if ".mod.html" in location else False
    return None
