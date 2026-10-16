"""Arthurimmo (arthurimmo.com, agency network) — HTML list pages scoped to Île-de-France.

List: https://www.arthurimmo.com/immobilier/location/immo-ile-de-france/bien-<appartement|maison>?sort=-created_at[&page=N]
      (the region page of the `immobilier/{transaction}/{localization}/bien-{type}` route;
      15 cards per page, newest first, ~2.5 MB per page because of an embedded tenant JSON)
Ad:   https://www.arthurimmo.com/annonces/location/<type>/<city>-<postal code>/<id>.htm

Cards are Livewire "property.card" components: title "Appartement | 3 pièces | 82 m²",
price "920 € /mois", "City 94370", a description and the photos. No DPE, posting date or
coordinates on the list page; furnished is inferred from the description. The postal code
in the card (and in the ad URL) is checked against the IDF departments as a safety net.

robots.txt: `User-agent: *` allows everything; the `Disallow: /` groups only target
barkrowler, Claudebot and Bytespider.
"""
from __future__ import annotations

import logging
import re
from html import unescape
from html.parser import HTMLParser
from typing import Iterator, Optional
from urllib.parse import urljoin

from ..model import IDF_DEPARTMENTS, Listing

log = logging.getLogger(__name__)

SLUG = "arthurimmo"
LABEL = "Arthurimmo"
COLOR = "#00529b"
MIN_INTERVAL = 1800  # each list page is ~2.5 MB
BASE = "https://www.arthurimmo.com"
TYPES = ("appartement", "maison")
HOUSING = {"appartement", "maison", "studio", "loft", "duplex"}

_AD_RE = re.compile(r"/annonces/location/([a-z-]+)/[^/]+-(\d{5})/(\d+)\.htm$")


def list_url(kind: str = "appartement", page: int = 1) -> str:
    url = f"{BASE}/immobilier/location/immo-ile-de-france/bien-{kind}?sort=-created_at"
    return url if page <= 1 else f"{url}&page={page}"


class _CardParser(HTMLParser):
    """Collects the fields of each Livewire property.card block."""

    def __init__(self):
        super().__init__()
        self.cards: list[dict] = []
        self._card: Optional[dict] = None
        self._depth = 0
        self._text_target: Optional[str] = None
        self._in_description = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        classes = cls.split()
        if tag == "div" and "property.card" in a.get("wire:initial-data", ""):
            self._card = {"photos": [], "title": "", "price": "", "place": "", "description": ""}
            self._depth = 1
            return
        if self._card is None:
            return
        if tag == "div":
            self._depth += 1
            if "text-orange-500" in classes and "font-semibold" in classes:
                self._text_target = "price"
            elif cls == "text-gray-600 text-sm":
                self._text_target = "place"
            elif "line-clamp-3" in classes:
                self._in_description = True
        elif tag == "a" and "/annonces/" in a.get("href", "") and "href" not in self._card:
            self._card["href"] = unescape(a["href"])
        elif tag == "img" and a.get("src", "").startswith("http"):
            src = unescape(a["src"])
            if src not in self._card["photos"]:
                self._card["photos"].append(src)
        elif tag == "h2":
            self._text_target = "title"
        elif tag == "p" and self._in_description:
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
            if self._text_target in ("price", "place"):
                self._text_target = None
            if self._in_description and self._text_target != "description":
                self._in_description = False
        elif tag == "h2" and self._text_target == "title":
            self._text_target = None
        elif tag == "p" and self._text_target == "description":
            self._text_target = None
            self._in_description = False

    def handle_data(self, data):
        if self._card is None or not self._text_target:
            return
        text = unescape(data).replace("\xa0", " ").strip()
        if text:
            self._card[self._text_target] = (self._card[self._text_target] + " " + text).strip()


def _int(text: str) -> Optional[int]:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def _furnished(description: str) -> Optional[bool]:
    """"non meublé" -> False; "meublé" (not about the kitchen) -> True; otherwise unknown."""
    if re.search(r"\bnon[- ]meubl", description, re.I):
        return False
    text = re.sub(r"cuisine[^.,;]{0,40}?meubl\w*", "", description, flags=re.I)
    return True if re.search(r"\bmeubl", text, re.I) else None


def parse_list(html: str) -> list[Listing]:
    parser = _CardParser()
    parser.feed(html)
    out = []
    for c in parser.cards:
        href = c.get("href")
        if not href:
            continue
        url = urljoin(BASE, href)
        m = _AD_RE.search(url)
        if not m:
            continue
        kind, url_pc, ad_id = m.groups()
        if kind not in HOUSING:
            continue
        if "/mois" not in c["price"]:
            continue
        pm = re.match(r"^(.*?)\s*(\d{5})$", c["place"])
        postal_code = pm.group(2) if pm else url_pc
        if postal_code[:2] not in IDF_DEPARTMENTS:
            continue
        city = (pm.group(1).strip() if pm else None) or None
        title = re.sub(r"\s*\|\s*", " | ", c["title"])
        rm = re.search(r"(\d+)\s*pièce", title)
        am = re.search(r"(\d+(?:[.,]\d+)?)\s*m²", title)
        furnished = _furnished(c["description"])
        out.append(Listing(
            id=f"{SLUG}:{ad_id}",
            source=SLUG,
            url=url,
            title=title + (f" - {city}" if city else ""),
            rent=_int(c["price"].split("€")[0]),
            charges=None,
            area=float(am.group(1).replace(",", ".")) if am else None,
            rooms=int(rm.group(1)) if rm else None,
            bedrooms=None,
            furnished=furnished,
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


def _get(session, url: str):
    """session.get, following one same-site redirect (the session does not follow them)."""
    resp = session.get(url)
    if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("Location"):
        resp = session.get(urljoin(url, resp.headers["Location"]))
    return resp


def fetch(session, departments: list[str], max_pages: int = 2) -> Iterator[Listing]:
    # The site has a region page but no per-department pages: `departments` is ignored and
    # every IDF ad is yielded (the parser drops anything outside the 8 departments).
    for kind in TYPES:
        for page in range(1, max_pages + 1):
            url = list_url(kind, page)
            resp = _get(session, url)
            if resp.status_code != 200:
                log.warning("arthurimmo: %s returned %s", url, resp.status_code)
                break
            listings = parse_list(resp.text)
            log.info("arthurimmo: %s page %d: %d ads", kind, page, len(listings))
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
        return None if "/annonces/" in location else False
    return None
