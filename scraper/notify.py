"""filter.json matching (Jinka vocabulary) and Discord webhook delivery."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import requests

from .model import Listing

log = logging.getLogger(__name__)

FILTER_FILE = Path(__file__).resolve().parent.parent / "filter.json"


def load_filter(path: Path = FILTER_FILE) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _ns(v):
    return v in (None, "", "ns", [])


def matches(l: Listing, f: dict) -> bool:
    """Apply a saved filter. Keys mirror Jinka's alert payload; "ns" / missing = not specified.

    rent_min, rent_max, area_min, area_max, room_min, bedroom_min: numbers
    furnished: "yes" | "no" | "ns"
    owner_type: "Particulier" | "Agence" | "ns"
    dpe: list of accepted classes, e.g. ["A","B","C","D"]; [] = any
    where: {"dpts": ["75","92"], "postalCodes": ["75011"]}; both empty = anywhere
    sources: list of source slugs; [] = any
    """
    if l.expired:
        return False
    if not _ns(f.get("rent_min")) and (l.rent is None or l.rent < f["rent_min"]):
        return False
    if not _ns(f.get("rent_max")) and (l.rent is None or l.rent > f["rent_max"]):
        return False
    if not _ns(f.get("area_min")) and (l.area is None or l.area < f["area_min"]):
        return False
    if not _ns(f.get("area_max")) and (l.area is None or l.area > f["area_max"]):
        return False
    if not _ns(f.get("room_min")) and (l.rooms is None or l.rooms < f["room_min"]):
        return False
    if not _ns(f.get("bedroom_min")) and (l.bedrooms is None or l.bedrooms < f["bedroom_min"]):
        return False
    if f.get("furnished") == "yes" and l.furnished is not True:
        return False
    if f.get("furnished") == "no" and l.furnished is True:
        return False
    if not _ns(f.get("owner_type")) and l.owner_type != f["owner_type"]:
        return False
    if f.get("dpe") and l.dpe not in f["dpe"]:
        return False
    if f.get("sources") and l.source not in f["sources"]:
        return False
    where = f.get("where") or {}
    dpts, pcs = where.get("dpts") or [], where.get("postalCodes") or []
    if dpts or pcs:
        pc = l.postal_code or ""
        if not (pc in pcs or pc[:2] in dpts):
            return False
    return True


def _summary(l: Listing) -> str:
    bits = []
    if l.area is not None:
        bits.append(f"{l.area:g} m²")
    if l.rooms is not None:
        bits.append(f"{l.rooms} p.")
    if l.bedrooms:
        bits.append(f"{l.bedrooms} ch.")
    if l.furnished is True:
        bits.append("meublé")
    if l.dpe:
        bits.append(f"DPE {l.dpe}")
    return " · ".join(bits)


def format_text(l: Listing, label: str) -> str:
    """Plain-text fallback, used when no webhook is configured."""
    rent = f"{l.rent} €" if l.rent is not None else "loyer n.c."
    place = " ".join(x for x in (l.city, l.postal_code) if x)
    who = f" · {l.owner_type}" if l.owner_type else ""
    return f"{rent} · {_summary(l)} — {place} — {label}{who}\n{l.url}"


def format_embed(l: Listing, label: str) -> dict:
    """One Discord embed per listing: https://discord.com/developers/docs/resources/message#embed-object"""
    rent = f"{l.rent} €" if l.rent is not None else "Loyer n.c."
    if l.charges is not None:
        rent += f" (dont {l.charges} € de charges)"
    place = " ".join(x for x in (l.city, l.postal_code) if x)
    embed = {
        "title": f"{rent} — {_summary(l) or l.title}"[:256],
        "url": l.url,
        "description": place,
        "footer": {"text": f"{label}{' · ' + l.owner_type if l.owner_type else ''}"},
    }
    if l.posted_at:
        embed["timestamp"] = l.posted_at
    if l.photos:
        embed["thumbnail"] = {"url": l.photos[0]}
    return embed


def send_discord(embeds: list[dict], webhook_url: str) -> bool:
    """POST up to 10 embeds in one webhook message."""
    resp = requests.post(webhook_url, json={"embeds": embeds[:10]}, timeout=30)
    if not resp.ok:
        log.error("discord: %s %s", resp.status_code, resp.text[:200])
    return resp.ok


def notify_new(new: list[Listing], labels: dict[str, str], max_messages: int = 20) -> int:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    f = load_filter()
    hits = [l for l in new if matches(l, f)]
    log.info("notify: %d new listings, %d match filter.json", len(new), len(hits))
    if not hits:
        return 0
    if not webhook:
        log.warning("notify: DISCORD_WEBHOOK_URL not set; printing instead")
        for l in hits:
            print(format_text(l, labels.get(l.source, l.source)))
        return 0
    chosen = hits[:max_messages]
    sent = 0
    for i in range(0, len(chosen), 10):
        batch = chosen[i:i + 10]
        if send_discord([format_embed(l, labels.get(l.source, l.source)) for l in batch], webhook):
            sent += len(batch)
    if len(hits) > max_messages:
        requests.post(webhook, json={"content": f"… et {len(hits) - max_messages} autres nouvelles annonces, voir le site."}, timeout=30)
    return sent
