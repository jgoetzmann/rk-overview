/* Build-time check for docs/demo.html.
 *
 * The demo page re-implements the Q15 integrator in JavaScript. This script loads the
 * published page, stubs just enough DOM for it to run headless, and drives its own
 * self-check: every (method, problem, rounding) case in the embedded fixture is
 * recomputed in JavaScript and compared, bit for bit, against the final int16 state
 * that rk_harness.simulate.solve_q15 produced. It also confirms the three charts and
 * both generated sentences render non-empty, so a page that throws never ships.
 *
 *   node tools/check_demo.js [path/to/demo.html]
 *
 * Exit 0 when every case matches and every region rendered; exit 1 otherwise.
 */
"use strict";
const fs = require("fs");
const path = require("path");

const page = process.argv[2] ||
  path.join(__dirname, "..", "docs", "demo.html");
const html = fs.readFileSync(page, "utf8");

const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
if (scripts.length !== 2) {
  console.error(`FAIL: expected 2 inline scripts in ${page}, found ${scripts.length}`);
  process.exit(1);
}

/* ------------------------------------------------------------------ DOM stub */
const nodes = new Map();
function el(id) {
  if (nodes.has(id)) return nodes.get(id);
  const n = {
    id, innerHTML: "", className: "",
    style: {},
    parentNode: { style: {} },
    handlers: {},
    addEventListener(type, fn) { this.handlers[type] = fn; },
    setAttribute() {},
    getAttribute() { return null; },
    querySelectorAll() { return []; },
  };
  nodes.set(id, n);
  return n;
}
let onReady = null;
global.window = {};
global.document = {
  getElementById: el,
  addEventListener(name, fn) { if (name === "DOMContentLoaded") onReady = fn; },
};

/* ------------------------------------------------------------------ run */
const runInThisContext = require("vm").runInThisContext;
try {
  runInThisContext(scripts[0], { filename: "demo-data" });
  runInThisContext(scripts[1], { filename: "demo-js" });
} catch (e) {
  console.error("FAIL: demo script threw on load:", e && e.message);
  process.exit(1);
}
if (typeof onReady !== "function") {
  console.error("FAIL: demo never registered a DOMContentLoaded handler");
  process.exit(1);
}

const t0 = Date.now();
try {
  onReady();
} catch (e) {
  console.error("FAIL: demo threw during first render:", e && e.stack);
  process.exit(1);
}

const REGIONS = ["board", "traj", "readout", "pareto", "rankline", "paretoline"];
const problems = [];
for (const id of REGIONS) {
  if (!el(id).innerHTML || el(id).innerHTML.length < 20) {
    problems.push(`region '${id}' rendered ${el(id).innerHTML.length} chars`);
  }
}

/* Drive every control combination a visitor can reach and make sure none of them throws,
 * renders an empty region, leaks NaN/undefined into the page, or emits an SVG coordinate
 * a browser would silently drop. */
const data = global.window.__RKDEMO__;
const click = (host, v) =>
  el(host).handlers.click({ target: { closest: () => ({ getAttribute: () => v }) } });
const strip = s => s.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
let combos = 0;
for (const mode of ["floor", "nearest"]) {
  for (const p of data.problems) {
    for (const m of data.methods) {
      try {
        click("modeseg", mode);
        click("probseg", p.name);
        click("methseg", m.key);
      } catch (e) {
        problems.push(`${mode}/${p.name}/${m.key} threw: ${e && e.message}`);
        continue;
      }
      combos++;
      for (const id of REGIONS) {
        const h = el(id).innerHTML;
        if (!h || h.length < 20) problems.push(`${mode}/${p.name}/${m.key}: ${id} empty`);
        const junk = strip(h).match(/NaN|undefined|Infinity/);
        if (junk) problems.push(`${mode}/${p.name}/${m.key}: ${id} rendered ${junk[0]}`);
        if (/(?:\bx|\by|cx|cy|width|height)="(?:NaN|-?Infinity)/.test(h)) {
          problems.push(`${mode}/${p.name}/${m.key}: ${id} has an invalid SVG coordinate`);
        }
      }
    }
  }
}
const DEADLINE = Date.now() + 120000;
const check = () => {
  const line = el("selfcheck").innerHTML;
  const done = /<b>(\d+) of (\d+)<\/b>/.exec(line);
  if (!done && Date.now() < DEADLINE) { setTimeout(check, 10); return; }
  const m = done;
  const cases = data.expected.filter(e => e.status === "ok").length;
  let ok = true;
  if (!m) {
    console.error("FAIL: self-check produced no count:", line.slice(0, 200));
    ok = false;
  } else if (m[1] !== m[2]) {
    console.error(`FAIL: only ${m[1]} of ${m[2]} browser runs matched the Python evaluator`);
    ok = false;
  } else {
    console.log(`demo self-check: ${m[1]} of ${m[2]} runs reproduce solve_q15 exactly ` +
                `(${cases} fixture cases, ${Date.now() - t0} ms)`);
  }
  for (const p of problems) { console.error("FAIL:", p); ok = false; }
  if (ok) {
    console.log(`demo render: ${combos} control combinations, ${REGIONS.length} regions ` +
                `each, no empty output and no invalid coordinates`);
  }
  process.exit(ok ? 0 : 1);
};
setTimeout(check, 5);
