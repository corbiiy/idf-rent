/* Runs in the search tab after parse.js. Its last expression is returned to the service worker. */
(() => {
  const P = globalThis.LbcParse;
  if (P.looksLikeChallenge(document)) return { status: "challenge", ads: [], url: location.href };
  let ads = [];
  const nd = document.getElementById("__NEXT_DATA__");
  if (nd) ads = P.parseNextData(nd.textContent);
  if (!ads.length) {
    const cards = [...document.querySelectorAll('a[data-qa-id="aditem_container"], a[href*="/ad/"]')].map((a) => {
      const q = (sel) => { const e = a.querySelector(sel); return e ? e.innerText.trim() : ""; };
      const texts = [...a.querySelectorAll("p, span")].map((e) => e.innerText.trim());
      const img = a.querySelector("img");
      return {
        href: a.getAttribute("href") || "",
        title: q('[data-qa-id="aditem_title"]') || a.getAttribute("title") || q("h2, h3, p"),
        price: q('[data-qa-id="aditem_price"]') || q('[data-test-id="price"]') || (texts.find((t) => /\d\s*€/.test(t)) || ""),
        details: texts.filter((t) => /m²|pièce|meubl/i.test(t)).join(" · "),
        place: texts.find((t) => /\b\d{5}\b/.test(t)) || "",
        img: img ? (img.currentSrc || img.src || "") : "",
      };
    });
    ads = P.parseCards(cards);
  }
  const sample = ads.length ? null : document.documentElement.outerHTML.slice(0, 200000);
  return { status: ads.length ? "ok" : "empty", ads, url: location.href, sample };
})();
