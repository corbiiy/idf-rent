/* idf-rent leboncoin alerts — service worker.
 *
 * Every `intervalSec` seconds (default 300, floor 180) it reloads one pinned, muted tab per
 * saved search URL, one search at a time with a pause between them, reads the ads with
 * content.js, keeps the ids already seen, runs the new ones through the idf-rent filter
 * (filter.json fetched from the repository) and posts matches to the Discord webhook.
 * A verification page stops the cycle: one Discord notice per hour and a "!" badge. Nothing is
 * retried, spoofed or solved; this is just your own browser opening your own searches.
 */
importScripts("filter.js");

const FILTER_URL = "https://raw.githubusercontent.com/corbiiy/idf-rent/main/filter.json";
const DEFAULTS = { searches: [], webhook: "", intervalSec: 300 };
const MIN_INTERVAL = 180;
const SEEN_CAP = 5000;
const CHALLENGE_NOTICE_EVERY = 3600 * 1000;
const FILTER_REFRESH_EVERY = 3600 * 1000;
const LABEL = "leboncoin";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const today = () => new Date().toISOString().slice(0, 10);

// ---------- storage helpers ----------
async function getSettings() {
  const s = await chrome.storage.local.get(["settings"]);
  return { ...DEFAULTS, ...(s.settings || {}) };
}
async function getState() {
  const s = await chrome.storage.local.get(["state"]);
  return { seen: {}, tabs: {}, lastCycle: null, results: {}, lastChallengeNotice: 0, todayCount: 0, todayDate: today(), filter: null, filterAt: 0, lastSample: null, log: [], ...(s.state || {}) };
}
async function setState(state) { await chrome.storage.local.set({ state }); }
function logLine(state, msg) {
  state.log = [`${new Date().toLocaleTimeString("fr-FR")} ${msg}`, ...(state.log || [])].slice(0, 50);
}

// ---------- filter.json from the repository ----------
async function currentFilter(state) {
  if (state.filter && Date.now() - state.filterAt < FILTER_REFRESH_EVERY) return state.filter;
  try {
    const r = await fetch(FILTER_URL, { cache: "no-store" });
    if (r.ok) { state.filter = await r.json(); state.filterAt = Date.now(); }
  } catch (e) { /* keep the cached copy */ }
  return state.filter || {};
}

// ---------- Discord ----------
function embed(l) {
  const bits = [];
  if (l.area != null) bits.push(`${l.area} m²`);
  if (l.rooms != null) bits.push(`${l.rooms} p.`);
  if (l.bedrooms) bits.push(`${l.bedrooms} ch.`);
  if (l.furnished === true) bits.push("meublé");
  if (l.dpe) bits.push(`DPE ${l.dpe}`);
  const rent = l.rent != null ? `${l.rent} €` : "Loyer n.c.";
  const e = {
    title: `${rent} — ${bits.join(" · ") || l.title}`.slice(0, 256),
    url: l.url,
    description: [l.city, l.postal_code].filter(Boolean).join(" "),
    footer: { text: `${LABEL}${l.owner_type ? " · " + l.owner_type : ""}` },
  };
  if (l.photos && l.photos[0]) e.thumbnail = { url: l.photos[0] };
  return e;
}
async function postDiscord(webhook, payload) {
  const r = await fetch(webhook, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  return r.ok;
}
async function notify(webhook, listings) {
  let sent = 0;
  for (let i = 0; i < Math.min(listings.length, 20); i += 10) {
    if (await postDiscord(webhook, { embeds: listings.slice(i, i + 10).map(embed) })) sent += Math.min(10, listings.length - i);
  }
  if (listings.length > 20) await postDiscord(webhook, { content: `… et ${listings.length - 20} autres nouvelles annonces leboncoin.` });
  return sent;
}

// ---------- tabs ----------
async function tabFor(url, state) {
  const id = state.tabs[url];
  if (id) {
    try { const t = await chrome.tabs.get(id); if (t) return t; } catch (e) { /* closed */ }
  }
  const t = await chrome.tabs.create({ url, active: false, pinned: true });
  try { await chrome.tabs.update(t.id, { muted: true }); } catch (e) { /* ignore */ }
  state.tabs[url] = t.id;
  return t;
}
function waitForLoad(tabId, timeoutMs = 45000) {
  return new Promise((resolve) => {
    const done = () => { chrome.tabs.onUpdated.removeListener(onUpd); clearTimeout(timer); resolve(); };
    const onUpd = (id, info) => { if (id === tabId && info.status === "complete") done(); };
    const timer = setTimeout(done, timeoutMs);
    chrome.tabs.onUpdated.addListener(onUpd);
  });
}
async function readSearch(url, state) {
  const tab = await tabFor(url, state);
  const loading = waitForLoad(tab.id);
  if (tab.url === url) await chrome.tabs.reload(tab.id); else await chrome.tabs.update(tab.id, { url });
  await loading;
  await sleep(2500 + Math.random() * 2000);
  const [res] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["parse.js", "content.js"] });
  return res && res.result ? res.result : { status: "empty", ads: [] };
}

// ---------- badge ----------
async function badge(state, text, color) {
  await chrome.action.setBadgeText({ text });
  await chrome.action.setBadgeBackgroundColor({ color });
}

// ---------- one cycle ----------
let running = false;
async function runCycle(trigger = "alarm") {
  if (running) return;
  running = true;
  try {
    const settings = await getSettings();
    const state = await getState();
    if (state.todayDate !== today()) { state.todayDate = today(); state.todayCount = 0; }
    if (!settings.searches.length) { logLine(state, "no search configured"); await setState(state); return; }
    const filter = await currentFilter(state);
    const firstRun = Object.keys(state.seen).length === 0;
    const fresh = [];
    let challenged = false;
    for (let i = 0; i < settings.searches.length; i++) {
      const url = settings.searches[i];
      if (i) await sleep(5000 + Math.random() * 5000);
      let res;
      try { res = await readSearch(url, state); } catch (e) { state.results[url] = { at: Date.now(), status: "error", detail: String(e) }; logLine(state, `error on search ${i + 1}: ${e}`); continue; }
      state.results[url] = { at: Date.now(), status: res.status, count: res.ads.length };
      if (res.status === "challenge") { challenged = true; logLine(state, "verification page on search " + (i + 1)); break; }
      if (res.status === "empty" && res.sample) state.lastSample = { at: Date.now(), url, html: res.sample };
      for (const l of res.ads) {
        if (state.seen[l.id]) continue;
        state.seen[l.id] = Date.now();
        fresh.push(l);
      }
    }
    // cap the seen set to the most recent entries
    const ids = Object.entries(state.seen).sort((a, b) => b[1] - a[1]).slice(0, SEEN_CAP);
    state.seen = Object.fromEntries(ids);

    if (challenged) {
      await badge(state, "!", "#c9282d");
      if (settings.webhook && Date.now() - state.lastChallengeNotice > CHALLENGE_NOTICE_EVERY) {
        state.lastChallengeNotice = Date.now();
        await postDiscord(settings.webhook, { content: "leboncoin asks for verification, open the pinned tab and solve it; alerts resume with the next cycle." });
      }
    } else {
      const hits = firstRun ? [] : fresh.filter((l) => LbcFilter.matches(l, filter));
      if (firstRun) logLine(state, `first cycle: ${fresh.length} ads recorded, no alert`);
      else logLine(state, `${trigger}: ${fresh.length} new ads, ${hits.length} match the filter`);
      if (hits.length && settings.webhook) await notify(settings.webhook, hits);
      state.todayCount += hits.length;
      await badge(state, state.todayCount ? String(state.todayCount) : "", "#1d6b3a");
    }
    state.lastCycle = Date.now();
    await setState(state);
  } finally {
    running = false;
  }
}

// ---------- scheduling ----------
async function schedule() {
  const s = await getSettings();
  const minutes = Math.max(MIN_INTERVAL, Number(s.intervalSec) || 300) / 60;
  await chrome.alarms.clear("cycle");
  await chrome.alarms.create("cycle", { periodInMinutes: minutes, delayInMinutes: 0.2 });
}
chrome.runtime.onInstalled.addListener(schedule);
chrome.runtime.onStartup.addListener(schedule);
chrome.alarms.onAlarm.addListener((a) => { if (a.name === "cycle") runCycle("alarm"); });
chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage());
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "run-now") { runCycle("manual").then(() => sendResponse({ ok: true })); return true; }
  if (msg && msg.type === "reschedule") { schedule().then(() => sendResponse({ ok: true })); return true; }
  if (msg && msg.type === "test-webhook") {
    getSettings().then((s) => postDiscord(s.webhook, { content: "idf-rent leboncoin alerts: test message, the webhook works." })).then((ok) => sendResponse({ ok })).catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true;
  }
  return false;
});
