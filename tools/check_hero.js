/* Build-time check for the landing widget in docs/index.html.
 *
 * The widget ranks eleven methods under both rounding modes from data reduced out of
 * demo_data.json. This loads the published page headless, drives every problem button
 * and every hover, and confirms the chart and its sentence render without NaN, empty
 * output or an SVG coordinate a browser would drop. It also re-derives the ranking in
 * plain JavaScript and checks the widget agrees, so a chart that silently mis-sorts
 * fails the build.
 *
 *   node tools/check_hero.js [path/to/index.html]
 */
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const page = process.argv[2] || path.join(__dirname, "..", "docs", "index.html");
const html = fs.readFileSync(page, "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
if (scripts.length !== 2) {
  console.error(`FAIL: expected 2 inline scripts in ${page}, found ${scripts.length}`);
  process.exit(1);
}

const nodes = new Map();
const mk = id => ({
  id, innerHTML: "", handlers: {},
  addEventListener(t, f) { this.handlers[t] = f; },
  setAttribute(k, v) { this.attrs = this.attrs || {}; this.attrs[k] = v; },
  getAttribute(k) { return (this.attrs || {})[k] ?? this.dataV ?? null; },
  querySelectorAll() { return []; },
});
const el = id => (nodes.has(id) ? nodes.get(id) : (nodes.set(id, mk(id)), nodes.get(id)));
let onReady = null;
global.window = {};
global.document = {
  getElementById: el,
  querySelectorAll() { return []; },
  addEventListener(n, f) { if (n === "DOMContentLoaded") onReady = f; },
};
try {
  vm.runInThisContext(scripts[0], { filename: "flip-data" });
  vm.runInThisContext(scripts[1], { filename: "flip-js" });
} catch (e) { console.error("FAIL: hero script threw on load:", e && e.message); process.exit(1); }
if (typeof onReady !== "function") { console.error("FAIL: no DOMContentLoaded handler"); process.exit(1); }
try { onReady(); } catch (e) { console.error("FAIL: hero threw on first render:", e && e.stack); process.exit(1); }

const H = global.window.__RKFLIP__;
const bad = [];
const strip = s => s.replace(/<[^>]+>/g, " ");
const click = v => el("flipseg").handlers.click({ target: { closest: () => ({ getAttribute: () => v }) } });
const hover = k => el("flip").handlers.mouseover({ target: { closest: () => (k ? { getAttribute: () => k } : null) } });

/* Independent ranking, so the chart is checked against something rather than itself. */
function expectRank(prob, mode) {
  const xs = H.methods.map((m, i) => ({ k: m.key, e: H.err[prob][mode][i] }))
    .filter(z => z.e !== null && isFinite(z.e) && z.e > 0)
    .sort((a, b) => a.e - b.e || (a.k < b.k ? -1 : 1));
  let prev = null, r = 0;
  xs.forEach((z, i) => { if (prev === null || z.e !== prev) { r = i + 1; prev = z.e; } z.r = r; });
  return xs;
}

let checked = 0, ranksChecked = 0;
for (const prob of H.problems) {
  click(prob);
  for (const k of [null, ...H.methods.map(m => m.key)]) {
    hover(k);
    checked++;
    for (const id of ["flip", "flipsay"]) {
      const h = el(id).innerHTML;
      if (!h || h.length < 20) bad.push(`${prob}/${k}: ${id} empty`);
      const junk = strip(h).match(/NaN|undefined|Infinity/);
      if (junk) bad.push(`${prob}/${k}: ${id} rendered ${junk[0]}`);
      if (/(?:\bx|\by|cx|cy|width|height)="(?:NaN|-?Infinity)/.test(h)) {
        bad.push(`${prob}/${k}: ${id} invalid SVG coordinate`);
      }
    }
  }
  // The left column must read in the ranking order the data implies, label for label.
  const label = Object.fromEntries(H.methods.map(m => [m.key, m.label]));
  const want = expectRank(prob, "floor").map(z => `${z.r} ${label[z.k]}`);
  const shown = [...el("flip").innerHTML.matchAll(
    /<text class="fn[^"]*"[^>]*text-anchor="end">(\d+)\s+(.*?)\s+<tspan/g)]
    .map(m => `${m[1]} ${m[2]}`);
  if (shown.length !== want.length) {
    bad.push(`${prob}: left column drew ${shown.length} rows, data implies ${want.length}`);
  } else if (shown.join("|") !== want.join("|")) {
    bad.push(`${prob}: left column order is ${shown.join(", ")}; data implies ${want.join(", ")}`);
  } else {
    ranksChecked += shown.length;
  }
}
console.log(`hero: ${H.methods.length} methods x ${H.problems.length} problems, ` +
            `${checked} render passes, ${ranksChecked} ranked rows matched against the data`);
if (bad.length) { bad.slice(0, 10).forEach(b => console.error("FAIL:", b)); process.exit(1); }
console.log("hero render: no empty output, no NaN, no invalid coordinates");
