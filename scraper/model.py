"""The common listing schema every source normalises into.

Field vocabulary follows the Jinka alert schema (owner_type Particulier/Agence,
dpe A-G, furnished yes/no) so the site can filter with the same words.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Listing:
    id: str                      # "<source>:<source id>"
    source: str                  # slug: "pap", "bienici"
    url: str                     # link to the original ad
    title: str
    rent: Optional[int]          # monthly rent, charges included, in EUR
    charges: Optional[int]       # monthly charges in EUR, if the source splits them
    area: Optional[float]        # m2
    rooms: Optional[int]
    bedrooms: Optional[int]
    furnished: Optional[bool]
    owner_type: Optional[str]    # "Particulier" | "Agence" | None
    dpe: Optional[str]           # "A".."G" | None
    postal_code: Optional[str]
    city: Optional[str]
    lat: Optional[float]
    lng: Optional[float]
    photos: list[str] = field(default_factory=list)
    posted_at: Optional[str] = None   # ISO 8601, as reported by the source
    first_seen: Optional[str] = None  # ISO 8601, set by the store
    last_seen: Optional[str] = None   # ISO 8601, set by the store
    expired: bool = False
    photo_hash: Optional[str] = None  # dHash of the first photo, for cross-source dedupe

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Listing":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


IDF_DEPARTMENTS = {
    "75": "Paris",
    "77": "Seine-et-Marne",
    "78": "Yvelines",
    "91": "Essonne",
    "92": "Hauts-de-Seine",
    "93": "Seine-Saint-Denis",
    "94": "Val-de-Marne",
    "95": "Val-d'Oise",
}
