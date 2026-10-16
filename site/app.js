(function () {
  "use strict";

  const STORAGE_FILTER = "idf-rent:filter";
  const STORAGE_LAST_VISIT = "idf-rent:last-visit";
  // On GitHub Pages read the file straight from the repository (fresh within ~5 minutes,
  // no redeploy needed); elsewhere (local server) use the file next to the site.
  const DATA_PATHS = (() => {
    const m = location.hostname.match(/^([^.]+)\.github\.io$/);
    const repo = location.pathname.split("/")[1];
    const raw = m && repo ? [`https://raw.githubusercontent.com/${m[1]}/${repo}/main/data/listings.json`] : [];
    return raw.concat(["data/listings.json", "../data/listings.json"]);
  })();
  const MAX_CARDS = 300;

  const form = document.getElementById("filter-form");
  const cardsEl = document.getElementById("cards");
  const countEl = document.getElementById("count");
  const emptyEl = document.getElementById("empty");
  const errorEl = document.getElementById("error");
  const metaEl = document.getElementById("meta");
  const sourcesEl = document.getElementById("sources");

  let listings = [];
  let sourceLabels = {};
  let lastVisit = null;

  function readStorage(key) {
    try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : null; } catch (e) { return null; }
  }
  function writeStorage(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* private mode: ignore */ }
  }

  // --- filter state <-> form -------------------------------------------------
  function readForm() {
    const fd = new FormData(form);
    const num = (k) => { const v = fd.get(k); return v === null || v === "" ? "ns" : Number(v); };
    return {
      rent_min: num("rent_min"), rent_max: num("rent_max"),
      area_min: num("area_min"), area_max: num("area_max"),
      room_min: fd.get("room_min") || "ns", bedroom_min: fd.get("bedroom_min") || "ns",
      furnished: fd.get("furnished") || "ns", owner_type: fd.get("owner_type") || "ns",
      dpe: fd.getAll("dpe"),
      where: {
        dpts: fd.getAll("dpts"),
        postalCodes: String(fd.get("postal_codes") || "").split(/[\s,;]+/).filter((s) => /^\d{5}$/.test(s)),
      },
      sources: fd.getAll("sources"),
      only_new: fd.get("only_new") === "on",
      show_expired: fd.get("show_expired") === "on",
      sort: fd.get("sort") || "newest",
    };
  }

  function writeForm(f) {
    if (!f) return;
    const setNum = (name, value) => { form.elements[name].value = value === "ns" || value == null ? "" : value; };
    setNum("rent_min", f.rent_min); setNum("rent_max", f.rent_max); setNum("area_min", f.area_min); setNum("area_max", f.area_max);
    form.elements.room_min.value = f.room_min || "ns";
    form.elements.bedroom_min.value = f.bedroom_min || "ns";
    form.elements.sort.value = f.sort || "newest";
    form.querySelectorAll('input[name="furnished"]').forEach((r) => { r.checked = r.value === (f.furnished || "ns"); });
    form.querySelectorAll('input[name="owner_type"]').forEach((r) => { r.checked = r.value === (f.owner_type || "ns"); });
    form.querySelectorAll('input[name="dpe"]').forEach((c) => { c.checked = (f.dpe || []).includes(c.value); });
    form.querySelectorAll('input[name="dpts"]').forEach((c) => { c.checked = ((f.where || {}).dpts || []).includes(c.value); });
    form.elements.postal_codes.value = ((f.where || {}).postalCodes || []).join(", ");
    form.querySelectorAll('input[name="sources"]').forEach((c) => { c.checked = (f.sources || []).includes(c.value); });
    form.elements.only_new.checked = !!f.only_new;
    form.elements.show_expired.checked = !!f.show_expired;
  }

  // --- matching (same vocabulary as scraper/notify.py) -----------------------
  function isNew(l) { return Boolean(lastVisit && l.first_seen && l.first_seen > lastVisit); }

  function matches(l, f) {
    const ns = (v) => v === "ns" || v == null || v === "";
    if (l.expired && !f.show_expired) return false;
    if (f.only_new && !isNew(l)) return false;
    if (!ns(f.rent_min) && !(l.rent != null && l.rent >= f.rent_min)) return false;
    if (!ns(f.rent_max) && !(l.rent != null && l.rent <= f.rent_max)) return false;
    if (!ns(f.area_min) && !(l.area != null && l.area >= f.area_min)) return false;
    if (!ns(f.area_max) && !(l.area != null && l.area <= f.area_max)) return false;
    if (!ns(f.room_min) && !(l.rooms != null && l.rooms >= Number(f.room_min))) return false;
    if (!ns(f.bedroom_min) && !(l.bedrooms != null && l.bedrooms >= Number(f.bedroom_min))) return false;
    if (f.furnished === "yes" && l.furnished !== true) return false;
    if (f.furnished === "no" && l.furnished === true) return false;
    if (!ns(f.owner_type) && l.owner_type !== f.owner_type) return false;
    if (f.dpe.length && !f.dpe.includes(l.dpe)) return false;
    if (f.sources.length && !f.sources.includes(l.source)) return false;
    const { dpts, postalCodes } = f.where;
    if (dpts.length || postalCodes.length) {
      const pc = l.postal_code || "";
      if (!(postalCodes.includes(pc) || dpts.includes(pc.slice(0, 2)))) return false;
    }
    return true;
  }

  const sorters = {
    newest: (a, b) => (b.first_seen || "").localeCompare(a.first_seen || ""),
    rent_asc: (a, b) => (a.rent ?? Infinity) - (b.rent ?? Infinity),
    area_desc: (a, b) => (b.area ?? -1) - (a.area ?? -1),
  };

  // --- rendering ---------------------------------------------------------------
  const fmtDate = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

  function el(tag, attrs, children) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else n.setAttribute(k, v);
    }
    for (const c of children || []) if (c) n.append(c);
    return n;
  }
  const text = (s) => document.createTextNode(s);

  function card(l) {
    const label = sourceLabels[l.source] || l.source;
    const specs = [];
    if (l.area != null) specs.push(`${l.area} m²`);
    if (l.rooms != null) specs.push(`${l.rooms} pièce${l.rooms > 1 ? "s" : ""}`);
    if (l.bedrooms) specs.push(`${l.bedrooms} ch.`);

    const tags = [];
    if (l.dpe) tags.push(el("span", { class: `tag dpe dpe-${l.dpe}`, text: `DPE ${l.dpe}` }));
    if (l.furnished === true) tags.push(el("span", { class: "tag", text: "Meublé" }));
    if (l.furnished === false) tags.push(el("span", { class: "tag", text: "Non meublé" }));
    if (l.owner_type) tags.push(el("span", { class: "tag", text: l.owner_type }));
    tags.push(el("span", { class: `source source-${l.source}`, text: label }));

    const photo = l.photos && l.photos[0]
      ? el("img", { class: "photo", src: l.photos[0], alt: "", loading: "lazy", referrerpolicy: "no-referrer" })
      : el("div", { class: "nophoto", text: "Pas de photo" });

    let badge = null;
    if (l.expired) badge = el("span", { class: "badge-expired", text: "Expirée" });
    else if (isNew(l)) badge = el("span", { class: "badge-new", text: "Nouveau" });

    const when = l.posted_at || l.first_seen;
    return el("li", { class: `card${l.expired ? " is-expired" : ""}` }, [
      badge,
      photo,
      el("div", { class: "body" }, [
        el("p", { class: "price" }, [
          text(l.rent != null ? `${l.rent.toLocaleString("fr-FR")} €` : "Loyer n.c."),
          el("small", { text: l.charges != null ? ` dont ${l.charges} € de charges` : " cc" }),
        ]),
        el("p", { class: "specs", text: specs.join(" · ") || l.title }),
        el("p", { class: "place", text: [l.city, l.postal_code].filter(Boolean).join(" ") }),
        when ? el("p", { class: "when", text: `Publiée ${fmtDate.format(new Date(when))}` }) : null,
        el("div", { class: "tags" }, tags),
        el("a", { class: "link", href: l.url, target: "_blank", rel: "noopener noreferrer", text: `Voir l'annonce sur ${label} ↗` }),
      ]),
    ]);
  }

  function render() {
    const f = readForm();
    writeStorage(STORAGE_FILTER, f);
    const shown = listings.filter((l) => matches(l, f)).sort(sorters[f.sort] || sorters.newest);
    cardsEl.replaceChildren(...shown.slice(0, MAX_CARDS).map(card));
    emptyEl.hidden = shown.length > 0;

    const active = listings.filter((l) => !l.expired).length;
    const newCount = listings.filter((l) => !l.expired && isNew(l)).length;
    const parts = [el("strong", { text: String(shown.length) }), text(` annonce${shown.length > 1 ? "s" : ""} sur ${active} actives`)];
    if (lastVisit) parts.push(text(` · ${newCount} nouvelle${newCount > 1 ? "s" : ""} depuis votre dernière visite`));
    if (shown.length > MAX_CARDS) parts.push(text(` · ${MAX_CARDS} premières affichées, affinez les filtres`));
    countEl.replaceChildren(...parts);
  }

  // --- boot ---------------------------------------------------------------------
  async function loadData() {
    let lastErr;
    for (const path of DATA_PATHS) {
      try {
        const r = await fetch(path, { cache: "no-cache" });
        if (r.ok) return r.json();
        lastErr = new Error(`${path}: HTTP ${r.status}`);
      } catch (e) { lastErr = e; }
    }
    throw lastErr || new Error("listings.json introuvable");
  }

  function buildSourceChips(sources) {
    sourcesEl.replaceChildren(...Object.entries(sources).map(([slug, info]) =>
      el("label", { class: "chip" }, [el("input", { type: "checkbox", name: "sources", value: slug }), text(" " + (info.label || slug))])
    ));
  }

  document.getElementById("reset-filters").addEventListener("click", () => {
    form.reset();
    form.querySelectorAll('input[name="sources"]').forEach((c) => { c.checked = false; });
    render();
  });
  form.addEventListener("input", render);
  form.addEventListener("change", render);
  form.addEventListener("submit", (e) => e.preventDefault());

  lastVisit = readStorage(STORAGE_LAST_VISIT);
  // On phones the filter panel would push the results below the fold: start it collapsed.
  if (window.matchMedia("(max-width: 899px)").matches) document.getElementById("filters").open = false;

  loadData().then((data) => {
    listings = data.listings || [];
    sourceLabels = Object.fromEntries(Object.entries(data.sources || {}).map(([k, v]) => [k, v.label || k]));
    buildSourceChips(data.sources || {});
    writeForm(readStorage(STORAGE_FILTER));
    const gen = data.generated_at ? fmtDate.format(new Date(data.generated_at)) : "?";
    metaEl.textContent = `${listings.length} annonces · mis à jour ${gen}`;
    render();
    // "Nouveau" compares first_seen against the previous visit; record this one now.
    writeStorage(STORAGE_LAST_VISIT, data.generated_at || new Date().toISOString());
  }).catch((err) => {
    metaEl.textContent = "Erreur de chargement";
    errorEl.hidden = false;
    errorEl.textContent = `Impossible de charger les annonces (${err.message}).`;
  });
})();
