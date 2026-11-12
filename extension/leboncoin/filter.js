/* Port of scraper/notify.py::matches() — the same alert filter as the Railway worker.
 * Classic script: importScripts()'d by background.js, require()'d by test.js. */
(function (root) {
  "use strict";
  const ns = (v) => v === undefined || v === null || v === "" || v === "ns" || (Array.isArray(v) && v.length === 0);

  function rentCap(l, f) {
    const byDpt = f.rent_max_by_dpt || {};
    const dept = (l.postal_code || "").slice(0, 2);
    if (!(dept in byDpt)) return f.rent_max;
    const rule = byDpt[dept];
    if (!Array.isArray(rule)) return rule;
    for (const tier of rule) {
      const above = tier.area_above;
      if (above === undefined || above === null || (l.area != null && l.area > above)) return "rent_max" in tier ? tier.rent_max : f.rent_max;
    }
    return f.rent_max;
  }

  function matches(l, f) {
    if (l.expired) return false;
    if (!ns(f.rent_min) && (l.rent == null || l.rent < f.rent_min)) return false;
    const cap = rentCap(l, f);
    if (!ns(cap) && (l.rent == null || l.rent > cap)) return false;
    if (!ns(f.area_min) && (l.area == null || l.area < f.area_min)) return false;
    if (!ns(f.area_max) && (l.area == null || l.area > f.area_max)) return false;
    if (!ns(f.room_min) && (l.rooms == null || l.rooms < f.room_min)) return false;
    if (!ns(f.bedroom_min) && (l.bedrooms == null || l.bedrooms < f.bedroom_min)) return false;
    if (f.furnished === "yes" && l.furnished !== true) return false;
    if (f.furnished === "no" && l.furnished === true) return false;
    if (!ns(f.owner_type) && l.owner_type !== f.owner_type) return false;
    if (Array.isArray(f.dpe) && f.dpe.length && !f.dpe.includes(l.dpe)) return false;
    if (Array.isArray(f.sources) && f.sources.length && !f.sources.includes(l.source)) return false;
    if ((f.blocked_sources || []).includes(l.source)) return false;
    const where = f.where || {};
    const dpts = where.dpts || [], pcs = where.postalCodes || [];
    if (dpts.length || pcs.length) {
      const pc = l.postal_code || "";
      if (!(pcs.includes(pc) || dpts.includes(pc.slice(0, 2)))) return false;
    }
    return true;
  }

  const api = { matches, rentCap };
  root.LbcFilter = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
