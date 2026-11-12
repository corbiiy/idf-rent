/* Parse a leboncoin search results page into idf-rent listings.
 * Classic script: used by content.js in the page (globalThis.LbcParse) and by test.js in node.
 * Port of the former local/leboncoin_parse.py (same field mapping). */
(function (root) {
  "use strict";
  const SLUG = "leboncoin";
  const BASE = "https://www.leboncoin.fr";
  const HOUSING = new Set(["appartement", "maison", "studio", "loft", "duplex", "1", "2"]);

  function walkAds(node, acc) {
    if (Array.isArray(node)) { for (const v of node) walkAds(v, acc); }
    else if (node && typeof node === "object") {
      if ("list_id" in node && "subject" in node) { acc.push(node); return acc; }
      for (const v of Object.values(node)) walkAds(v, acc);
    }
    return acc;
  }

  const num = (v) => { if (v == null || v === "") return null; const n = parseFloat(String(v).replace(",", ".").replace(/\s/g, "")); return Number.isFinite(n) ? n : null; };
  const int = (v) => { const n = num(v); return n == null ? null : Math.round(n); };

  function adToListing(ad) {
    const attrs = {};
    for (const a of ad.attributes || []) if (a && a.key) attrs[a.key] = a;
    const kind = attrs.real_estate_type || {};
    const kindLabel = String(kind.value_label || kind.value || "").toLowerCase();
    if (kindLabel && !HOUSING.has(kindLabel)) return null;
    let price = ad.price;
    if (Array.isArray(price)) price = price.length ? price[0] : null;
    const loc = ad.location || {};
    const images = ad.images || {};
    let photos = (images.urls_large || images.urls || []).filter((u) => typeof u === "string");
    if (!photos.length && images.thumb_url) photos = [images.thumb_url];
    const f = String((attrs.furnished || {}).value_label || (attrs.furnished || {}).value || "").toLowerCase();
    const furnished = ["meublé", "meuble", "1"].includes(f) ? true : ["non meublé", "non meuble", "2"].includes(f) ? false : null;
    const dpe = String((attrs.energy_rate || {}).value || "").toUpperCase();
    let url = ad.url || `${BASE}/ad/locations/${ad.list_id}`;
    if (url.startsWith("/")) url = BASE + url;
    const owner = (ad.owner || {}).type;
    return {
      id: `${SLUG}:${ad.list_id}`, source: SLUG, url, title: String(ad.subject || "").trim(),
      rent: int(price), charges: null, area: num((attrs.square || {}).value),
      rooms: int((attrs.rooms || {}).value), bedrooms: int((attrs.bedrooms || {}).value), furnished,
      owner_type: owner === "private" ? "Particulier" : owner === "pro" ? "Agence" : null,
      dpe: /^[A-G]$/.test(dpe) ? dpe : null,
      postal_code: loc.zipcode ? String(loc.zipcode) : null, city: loc.city || null,
      lat: loc.lat ?? null, lng: loc.lng ?? null, photos,
      posted_at: ad.first_publication_date || ad.index_date || null,
    };
  }

  function parseNextData(json) {
    let data = json;
    if (typeof json === "string") { try { data = JSON.parse(json); } catch (e) { return []; } }
    const out = [], seen = new Set();
    for (const ad of walkAds(data, [])) {
      const l = adToListing(ad);
      if (l && !seen.has(l.id)) { seen.add(l.id); out.push(l); }
    }
    return out;
  }

  const M2 = /(\d+(?:[.,]\d+)?)\s*m²/, ROOMS = /(\d+)\s*pi[èe]ce/, PLACE = /^(.*?)\s*(\d{5})\s*$/, ID = /\/(\d{6,})(?:[/?#].*)?$/;

  function cardToListing(card) {
    const href = card.href || "";
    const m = ID.exec(href);
    if (!m) return null;
    const details = card.details || "";
    const area = M2.exec(details), rooms = ROOMS.exec(details), place = PLACE.exec((card.place || "").trim());
    const priceDigits = (card.price || "").replace(/[^\d]/g, "");
    const low = details.toLowerCase();
    return {
      id: `${SLUG}:${m[1]}`, source: SLUG, url: href.startsWith("http") ? href : BASE + href,
      title: String(card.title || "").trim(), rent: priceDigits ? parseInt(priceDigits, 10) : null, charges: null,
      area: area ? num(area[1]) : null, rooms: rooms ? parseInt(rooms[1], 10) : null, bedrooms: null,
      furnished: low.includes("meublé") && !low.includes("non meublé") ? true : null, owner_type: null, dpe: null,
      postal_code: place ? place[2] : null, city: place ? (place[1].trim() || null) : (card.place || null),
      lat: null, lng: null, photos: card.img ? [card.img] : [], posted_at: null,
    };
  }

  function parseCards(cards) {
    const out = [], seen = new Set();
    for (const c of cards || []) { const l = cardToListing(c); if (l && !seen.has(l.id)) { seen.add(l.id); out.push(l); } }
    return out;
  }

  /* A DataDome verification page: a captcha-delivery iframe or script, or an almost empty document. */
  function looksLikeChallenge(doc) {
    if (doc.querySelector('iframe[src*="captcha-delivery"], script[src*="captcha-delivery"]')) return true;
    const text = (doc.body && doc.body.innerText || "").trim();
    return !doc.getElementById("__NEXT_DATA__") && !doc.querySelector('a[href*="/ad/"]') && text.length < 200;
  }

  const api = { SLUG, parseNextData, parseCards, adToListing, cardToListing, looksLikeChallenge, walkAds };
  root.LbcParse = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
