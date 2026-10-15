"""filter.json matching (Jinka vocabulary) and Telegram delivery."""
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


def format_message(l: Listing, label: str) -> str:
    bits = []
    if l.rent is not None:
        bits.append(f"{l.rent} €")
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
    place = " ".join(x for x in (l.city, l.postal_code) if x)
    who = l.owner_type or ""
    return f"🏠 <b>{' · '.join(bits)}</b>\n{place} — {label}{' · ' + who if who else ''}\n{l.url}"


def send_telegram(text: str, token: str, chat_id: str) -> bool:
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False},
        timeout=30,
    )
    if not resp.ok:
        log.error("telegram: %s %s", resp.status_code, resp.text[:200])
    return resp.ok


def notify_new(new: list[Listing], labels: dict[str, str], max_messages: int = 20) -> int:
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    f = load_filter()
    hits = [l for l in new if matches(l, f)]
    log.info("notify: %d new listings, %d match filter.json", len(new), len(hits))
    if not hits:
        return 0
    if not token or not chat_id:
        log.warning("notify: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set; printing instead")
        for l in hits:
            print(format_message(l, labels.get(l.source, l.source)).replace("<b>", "").replace("</b>", ""))
        return 0
    sent = 0
    for l in hits[:max_messages]:
        if send_telegram(format_message(l, labels.get(l.source, l.source)), token, chat_id):
            sent += 1
    if len(hits) > max_messages:
        send_telegram(f"… et {len(hits) - max_messages} autres nouvelles annonces, voir le site.", token, chat_id)
    return sent
