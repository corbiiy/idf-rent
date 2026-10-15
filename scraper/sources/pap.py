"""PAP (pap.fr, "De Particulier à Particulier") — HTML list pages.

Every ad on PAP is posted by a private owner, so owner_type is always "Particulier".

List page: https://www.pap.fr/annonce/location-appartement-maison-<dept slug>-g<geo id>[-<page>]
Cards are <div class="search-list-item-alt"> blocks; the list card carries no posting date
and often no postal code (only the one embedded in the ad URL slug, when present).

Note: as of October 2026 pap.fr serves a Cloudflare JavaScript challenge (HTTP 403,
"cf-mitigated: challenge") to every non-browser client, robots.txt included. This module
does not try to work around that: on 403 the PoliteSession raises SourceBlocked and the
run moves on to the next source. The parser is kept tested against a saved fixture so it
works the day PAP exposes its pages (or an RSS feed) to plain clients again.
"""
from __future__ import annotations

import logging
import re
from html import unescape
from html.parser import HTMLParser
from typing import Iterator, Optional

from ..model import Listing

log = logging.getLogger(__name__)

SLUG = "pap"
LABEL = "PAP"
BASE = "https://www.pap.fr"

# department code -> (url slug, PAP geo id), ids from https://www.pap.fr/json/ac-geo?q=<dept>
GEO = {
    "75": ("paris-75", 439),
    "77": ("seine-et-marne-77", 441),
    "78": ("yvelines-78", 442),
    "91": ("essonne-91", 455),
    "92": ("hauts-de-seine-92", 456),
    "93": ("seine-saint-denis-93", 457),
    "94": ("val-de-marne-94", 458),
    "95": ("val-d-oise-95", 459),
}


def list_url(dept: str, page: int = 1) -> str:
    slug, geo = GEO[dept]
    suffix = f"-{page}" if page > 1 else ""
    return f"{BASE}/annonce/location-appartement-maison-{slug}-g{geo}{suffix}"


class _CardParser(HTMLParser):
    """Collects the fields of each search-list-item-alt card."""

    def __init__(self):
        super().__init__()
        self.cards: list[dict] = []
        self._card: Optional[dict] = None
        self._depth = 0
        self._text_target: Optional[str] = None
        self._in_tags = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if tag == "div" and "search-list-item-alt" in cls.split():
            self._card = {"photos": [], "tags": [], "dpe": None, "description": ""}
            self._depth = 1
            return
        if self._card is None:
            return
        if tag == "div":
            self._depth += 1
            m = re.search(r"item-thumb-dpe-([a-g])\b", cls)
            if m:
                self._card["dpe"] = m.group(1).upper()
        elif tag == "img" and a.get("src", "").startswith("http"):
            self._card["photos"].append(a["src"])
        elif tag == "a" and "item-title" in cls.split():
            self._card["href"] = a.get("href")
            self._card["id"] = a.get("name")
        elif tag == "span" and cls == "item-price":
            self._text_target = "price"
        elif tag == "span" and cls == "h1":
            self._text_target = "city"
        elif tag == "ul" and cls == "item-tags":
            self._in_tags = True
        elif tag == "li" and self._in_tags:
            self._text_target = "tag"
        elif tag == "p" and "item-description" in cls.split():
            self._text_target = "description"

    def handle_endtag(self, tag):
        if self._card is None:
            return
        if tag == "div":
            self._depth -= 1
            if self._depth == 0:
                self.cards.append(self._card)
                self._card = None
                return
        if tag == "ul":
            self._in_tags = False
        if tag in ("span", "li", "p"):
            self._text_target = None

    def handle_data(self, data):
        if self._card is None or not self._text_target:
            return
        text = unescape(data).replace("\xa0", " ").strip()
        if not text:
            return
        if self._text_target == "tag":
            self._card["tags"].append(text)
        elif self._text_target == "description":
            self._card["description"] += text + " "
        else:
            self._card[self._text_target] = (self._card.get(self._text_target, "") + " " + text).strip()


def _int(text: str) -> Optional[int]:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def parse_list(html: str) -> list[Listing]:
    parser = _CardParser()
    parser.feed(html)
    out = []
    for c in parser.cards:
        if not c.get("id") or not c.get("href"):
            continue
        rooms = bedrooms = None
        area = None
        for t in c["tags"]:
            if "pièce" in t:
                rooms = _int(t)
            elif "chambre" in t:
                bedrooms = _int(t)
            elif "m²" in t:
                area = _int(t)
        city = c.get("city", "")
        pc = re.search(r"\b(\d{5})\b", city) or re.search(r"-(\d{5})-r\d+$", c["href"])
        postal_code = pc.group(1) if pc else None
        description = c["description"].strip()
        furnished = True if re.search(r"\bmeubl", description, re.I) else None
        out.append(Listing(
            id=f"{SLUG}:{c['id']}",
            source=SLUG,
            url=BASE + c["href"],
            title=(f"{rooms} pièces" if rooms else "Logement") + (f" {area} m²" if area else "") + f" - {re.sub(r'\s*\(\d{5}\)', '', city)}",
            rent=_int(c.get("price", "")),
            charges=None,
            area=area,
            rooms=rooms,
            bedrooms=bedrooms,
            furnished=furnished,
            owner_type="Particulier",
            dpe=c.get("dpe"),
            postal_code=postal_code,
            city=re.sub(r"\s*\(\d{5}\)", "", city).strip() or None,
            lat=None,
            lng=None,
            photos=c["photos"],
            posted_at=None,
        ))
    return out


def fetch(session, departments: list[str], max_pages: int = 2) -> Iterator[Listing]:
    for dept in departments:
        if dept not in GEO:
            log.warning("pap: no geo id for department %s", dept)
            continue
        for page in range(1, max_pages + 1):
            resp = session.get(list_url(dept, page))
            if resp.status_code != 200:
                log.warning("pap: %s returned %s", resp.url, resp.status_code)
                break
            listings = parse_list(resp.text)
            log.info("pap: dept %s page %d: %d ads", dept, page, len(listings))
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
        # PAP redirects deleted ads to the list page
        location = resp.headers.get("Location", "")
        return "/annonces/" in location
    return None
