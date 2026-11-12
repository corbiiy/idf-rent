// Plain node tests: `node extension/leboncoin/test.js`. Mirror the Python filter tests.
const assert = require("assert");
const { matches, rentCap } = require("./filter.js");
const P = require("./parse.js");

const mk = (o) => ({ id: "leboncoin:1", source: "leboncoin", url: "https://x/1", title: "t", rent: 1000, charges: null, area: 30, rooms: 2, bedrooms: 1, furnished: true, owner_type: "Particulier", dpe: "C", postal_code: "75011", city: "Paris", lat: null, lng: null, photos: [], posted_at: null, ...o });

// area-tiered caps (same cases as tests/test_core.py)
const tiers = { rent_max: 675, rent_max_by_dpt: { 75: [{ area_above: 24, rent_max: 1050 }, { rent_max: 675 }] } };
assert.ok(matches(mk({ postal_code: "75011", area: 30, rent: 1000 }), tiers));
assert.ok(!matches(mk({ postal_code: "75011", area: 30, rent: 1100 }), tiers));
assert.ok(matches(mk({ postal_code: "75011", area: 20, rent: 650 }), tiers));
assert.ok(!matches(mk({ postal_code: "75011", area: 20, rent: 700 }), tiers));
assert.ok(!matches(mk({ postal_code: "75011", area: 24, rent: 700 }), tiers));
assert.ok(matches(mk({ postal_code: "75011", area: 24.5, rent: 700 }), tiers));
assert.ok(!matches(mk({ postal_code: "75011", area: null, rent: 700 }), tiers));
assert.ok(matches(mk({ postal_code: "92120", area: 30, rent: 670 }), tiers));
assert.ok(!matches(mk({ postal_code: "92120", area: 30, rent: 700 }), tiers));
assert.strictEqual(rentCap(mk({ postal_code: "75011", area: 30 }), tiers), 1050);
// number form still works
assert.ok(matches(mk({ postal_code: "75011", rent: 1000 }), { rent_max: 750, rent_max_by_dpt: { 75: 1050 } }));
// postal-code-only zone, blocked sources, area/room minimums
const zone = { where: { dpts: [], postalCodes: ["75011", "92120"] }, area_min: 14, room_min: 1, blocked_sources: ["locservice"] };
assert.ok(matches(mk({ postal_code: "75011" }), zone));
assert.ok(!matches(mk({ postal_code: "75012" }), zone));
assert.ok(!matches(mk({ postal_code: null }), zone));
assert.ok(!matches(mk({ area: 12 }), zone));
assert.ok(!matches(mk({ source: "locservice" }), zone));
assert.ok(matches(mk({}), {}));

// parser: synthetic __NEXT_DATA__ (no real ads)
const nd = { props: { pageProps: { searchData: { ads: [
  { list_id: 1000000001, first_publication_date: "2026-10-21 09:12:00", subject: "Studio meublé 18 m² Paris 11", url: "https://www.leboncoin.fr/ad/locations/1000000001", price: [850],
    images: { urls: ["https://img.example/1.jpg"], urls_large: ["https://img.example/1-large.jpg"] },
    attributes: [{ key: "real_estate_type", value: "1", value_label: "Appartement" }, { key: "square", value: "18" }, { key: "rooms", value: "1" }, { key: "furnished", value: "1", value_label: "Meublé" }, { key: "energy_rate", value: "d" }],
    location: { city: "Paris", zipcode: "75011", lat: 48.8585, lng: 2.3798 }, owner: { type: "private" } },
  { list_id: 1000000002, subject: "Appartement 2 pièces Montrouge", url: "/ad/locations/1000000002", price: [740], images: { urls: [] },
    attributes: [{ key: "real_estate_type", value: "1", value_label: "Appartement" }, { key: "square", value: "35" }, { key: "rooms", value: "2" }, { key: "bedrooms", value: "1" }, { key: "furnished", value: "2", value_label: "Non meublé" }],
    location: { city: "Montrouge", zipcode: "92120" }, owner: { type: "pro" } },
  { list_id: 1000000003, subject: "Place de parking", url: "/ad/locations/1000000003", price: [90], attributes: [{ key: "real_estate_type", value: "4", value_label: "Parking" }], location: { zipcode: "75015" } },
] } } } };
const ads = P.parseNextData(JSON.stringify(nd));
assert.deepStrictEqual(ads.map((a) => a.id), ["leboncoin:1000000001", "leboncoin:1000000002"]);
const [a, b] = ads;
assert.deepStrictEqual([a.rent, a.area, a.rooms, a.furnished, a.dpe, a.postal_code, a.city, a.owner_type], [850, 18, 1, true, "D", "75011", "Paris", "Particulier"]);
assert.deepStrictEqual(a.photos, ["https://img.example/1-large.jpg"]);
assert.strictEqual(a.posted_at, "2026-10-21 09:12:00");
assert.deepStrictEqual([b.rent, b.bedrooms, b.furnished, b.owner_type, b.url], [740, 1, false, "Agence", "https://www.leboncoin.fr/ad/locations/1000000002"]);
assert.deepStrictEqual(P.parseNextData("not json"), []);
// card fallback
const cards = P.parseCards([{ href: "/ad/locations/1000000009?from=list", title: "T2 lumineux", price: "920 €", details: "2 pièces · 38 m² · Meublé", place: "Paris 75012", img: "https://img.example/9.jpg" }, { href: "/boutique/123" }]);
assert.strictEqual(cards.length, 1);
assert.deepStrictEqual([cards[0].id, cards[0].rent, cards[0].area, cards[0].rooms, cards[0].furnished, cards[0].postal_code, cards[0].city], ["leboncoin:1000000009", 920, 38, 2, true, "75012", "Paris"]);
// challenge detection on a minimal DOM stand-in
const fakeDoc = (hasIframe, text, hasNext) => ({ querySelector: (sel) => (hasIframe && sel.includes("captcha-delivery")) ? {} : null, getElementById: () => (hasNext ? {} : null), body: { innerText: text } });
assert.ok(P.looksLikeChallenge(fakeDoc(true, "", false)));
assert.ok(P.looksLikeChallenge(fakeDoc(false, "", false)));
assert.ok(!P.looksLikeChallenge(fakeDoc(false, "lots of text ".repeat(50), true)));
console.log("extension tests OK");
