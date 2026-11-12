const $ = (id) => document.getElementById(id);
const msg = (t, ok = true) => { $("msg").textContent = t; $("msg").className = ok ? "ok" : "bad"; setTimeout(() => ($("msg").textContent = ""), 4000); };

async function load() {
  const { settings = {}, state = {} } = await chrome.storage.local.get(["settings", "state"]);
  $("searches").value = (settings.searches || []).join("\n");
  $("webhook").value = settings.webhook || "";
  $("interval").value = settings.intervalSec || 300;
  renderState(state);
}

function renderState(state) {
  const items = [];
  items.push(`<li>Dernier cycle : ${state.lastCycle ? new Date(state.lastCycle).toLocaleString("fr-FR") : "jamais"}</li>`);
  items.push(`<li>Annonces connues : ${Object.keys(state.seen || {}).length} · alertes aujourd'hui : ${state.todayCount || 0}</li>`);
  items.push(`<li>Filtre du dépôt : ${state.filterAt ? "chargé " + new Date(state.filterAt).toLocaleString("fr-FR") : "pas encore chargé"}</li>`);
  for (const [url, r] of Object.entries(state.results || {})) {
    const cls = r.status === "ok" ? "ok" : "bad";
    const what = r.status === "ok" ? `${r.count} annonces` : r.status === "challenge" ? "page de vérification" : r.status === "empty" ? "aucune annonce reconnue" : `erreur : ${r.detail || ""}`;
    items.push(`<li><span class="${cls}">●</span> ${new Date(r.at).toLocaleTimeString("fr-FR")} — ${what} — <span style="color:var(--muted)">${url.slice(0, 80)}</span></li>`);
  }
  $("status").innerHTML = items.join("");
  $("log").textContent = (state.log || []).join("\n");
  $("sampleBox").hidden = !state.lastSample;
}

$("save").addEventListener("click", async () => {
  const searches = $("searches").value.split(/\r?\n/).map((s) => s.trim()).filter((s) => s.startsWith("https://www.leboncoin.fr/"));
  const webhook = $("webhook").value.trim();
  const intervalSec = Math.max(180, parseInt($("interval").value, 10) || 300);
  $("interval").value = intervalSec;
  await chrome.storage.local.set({ settings: { searches, webhook, intervalSec } });
  await chrome.runtime.sendMessage({ type: "reschedule" });
  msg(`Enregistré : ${searches.length} recherche(s), cycle toutes les ${intervalSec} s.`);
});

$("test").addEventListener("click", async () => {
  const r = await chrome.runtime.sendMessage({ type: "test-webhook" });
  msg(r && r.ok ? "Message de test envoyé sur Discord." : "Échec : vérifiez l'URL du webhook (enregistrez d'abord).", !!(r && r.ok));
});

$("run").addEventListener("click", async () => {
  msg("Cycle en cours…");
  await chrome.runtime.sendMessage({ type: "run-now" });
  const { state = {} } = await chrome.storage.local.get(["state"]);
  renderState(state);
  msg("Cycle terminé.");
});

$("downloadSample").addEventListener("click", async () => {
  const { state = {} } = await chrome.storage.local.get(["state"]);
  if (!state.lastSample) return;
  const blob = new Blob([state.lastSample.html], { type: "text/html" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "leboncoin-sample.html";
  a.click();
});

chrome.storage.onChanged.addListener((changes) => { if (changes.state) renderState(changes.state.newValue || {}); });
load();
