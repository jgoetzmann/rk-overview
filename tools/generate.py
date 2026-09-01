"""Build the rk-overview site into docs/.

Snapshot semantics: run by hand, reads the live rk-work archive plus tools/floor_round.json,
copies the current rk-findings pages under docs/findings/, and writes five authored pages.
Reuses the findings site's style and chart primitives so the two sites read as one system.
Timezone policy: stored data is UTC; anything rendered for humans goes through
rk_harness.timefmt (US Central), and SNAPSHOT_DATE is a Central-time date.

    set PYTHONPATH=..\\rk-harness  (and RK_WORK_DIR to ..\\rk-work)
    python tools/generate.py
"""
from __future__ import annotations

import json
import math
import shutil
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent            # rk-overview/
WS = ROOT.parent              # workspace
sys.path.insert(0, str(WS / "rk-harness"))
sys.path.insert(0, str(HERE))

import pages_text as T  # noqa: E402
from rk_harness import archive, sitegen as sg  # noqa: E402
from rk_harness import costmodel, enumeration  # noqa: E402
from rk_harness import tableau as tableau_mod  # noqa: E402
from rk_harness import timefmt  # noqa: E402

SNAPSHOT_DATE = "2026-09-01"   # the date the snapshot was taken, US Central
DOCS = ROOT / "docs"

_EXTRA_STYLE = """
.hero{font-size:17px;max-width:78ch}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:900px){.two{grid-template-columns:1fr}}
.decision{background:var(--surface-1);border:1px solid var(--line);border-radius:10px;
  padding:16px 20px;margin:14px 0}
.decision h3{margin:0 0 6px;font-size:15px;color:var(--text-1)}
.decision .orig{color:var(--text-2);border-left:3px solid var(--line);padding-left:12px;margin:8px 0}
.decision .asbuilt{margin:8px 0 0}
.decision .tag{display:inline-block;padding:1px 8px;border-radius:99px;font-size:11px;
  font-weight:600;margin-left:8px;vertical-align:2px}
.tag-kept{background:var(--good-bg);color:var(--good-fg)}
.tag-changed{background:var(--warn-bg);color:var(--warn-fg)}
svg .box{fill:var(--surface-1);stroke:var(--line)}
svg .boxhl{fill:var(--surface-0);stroke:var(--s1);stroke-width:1.5}
svg .arrow{stroke:var(--text-3);fill:none;marker-end:url(#ah)}
svg .bt{font-weight:600;fill:var(--text-1)}
svg .bs{fill:var(--text-2);font-size:10px}
details.howto{margin:8px 0 4px;font-size:13px;color:var(--text-2)}
details.howto summary{cursor:pointer;color:var(--s1);font-size:12.5px;font-weight:600;
  list-style-position:inside}
details.howto>div{border-left:3px solid var(--line);padding:2px 0 2px 12px;margin-top:6px}
details.howto p{max-width:76ch;margin:6px 0}
ul.toc{columns:2;column-gap:32px;font-size:13px;margin:8px 0 4px;padding-left:20px}
ul.toc li{margin:2px 0}
@media (max-width:700px){ul.toc{columns:1}}
.decision{scroll-margin-top:16px}
.decision:target{border-color:var(--s1)}
.p0wrap{min-width:780px}
.p0head,details.p0 summary{display:grid;
  grid-template-columns:18px 80px 130px 88px 118px 148px 1fr;
  gap:10px;align-items:center;padding:7px 12px}
.p0head{font-size:12px;color:var(--text-2);font-weight:600;letter-spacing:.02em}
details.p0{background:var(--surface-1);border:1px solid var(--line);border-radius:8px;
  margin:6px 0;font-size:13px}
details.p0 summary{cursor:pointer;list-style:none;font-variant-numeric:tabular-nums}
details.p0 summary::-webkit-details-marker{display:none}
details.p0 summary::before{content:"+";color:var(--text-3);font-weight:600}
details.p0[open] summary::before{content:"\\2212"}
details.p0[open] summary{border-bottom:1px solid var(--line)}
.p0body{padding:10px 16px 12px 40px}
"""

_NAV = (
    ("index.html", "overview"),
    ("architecture.html", "architecture"),
    ("methodology.html", "methodology"),
    ("design-decisions.html", "design decisions"),
    ("results.html", "results"),
    ("findings/index.html", f"findings snapshot ({SNAPSHOT_DATE})"),
)

_ABOUT = T.ABOUT_NOTE.format(date=SNAPSHOT_DATE)


def _nav(active: str) -> str:
    links = "".join(
        f'<a href="{href}"{" class=" + chr(34) + "on" + chr(34) if href == active else ""}>{sg._esc(label)}</a>'
        for href, label in _NAV)
    links += '<a href="https://jgoetzmann.github.io/rk-findings/">live findings ↗</a>'
    return f'<nav class="tabs">{links}</nav>'


def _page(title: str, body: str, active: str, subtitle: str = "") -> str:
    sub = f'<p class="sub">{sg._esc(subtitle)}</p>' if subtitle else ""
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{sg._esc(title)}</title>\n"
        f"<style>{sg._STYLE}{_EXTRA_STYLE}</style>\n</head>\n<body>\n"
        '<header class="site"><div class="wrap">\n'
        f'<p class="banner">{sg._esc(_ABOUT)}</p>\n'
        f"<h1>{sg._esc(title)}</h1>\n{sub}\n"
        f"{_nav(active)}\n"
        "</div></header>\n"
        '<div class="wrap">\n'
        f"{body}\n"
        f"<footer>rk-overview — snapshot {SNAPSHOT_DATE} (US Central); the live numbers are on rk-findings.</footer>\n"
        "</div>\n</body>\n</html>\n"
    )


def _howto(body_html: str) -> str:
    """A short expandable explainer rendered under a diagram, chart, or table."""
    return ('<details class="howto"><summary>How to read this</summary>'
            f"<div>{body_html}</div></details>")


def _panel(inner: str, howto: str = "") -> str:
    """Panel wrapper; the howto is only attached when there is a chart to explain."""
    if not inner:
        return ""
    return '<div class="panel">' + inner + (_howto(howto) if howto else "") + "</div>"


# ----------------------------------------------------------------------------- diagrams

def _defs() -> str:
    return ('<defs><marker id="ah" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">'
            '<path d="M0,0 L8,4 L0,8 z" fill="var(--text-3)"/></marker></defs>')


def _box(x, y, w, h, title, lines, hl=False) -> str:
    cls = "boxhl" if hl else "box"
    out = [f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="8"/>',
           f'<text class="bt" x="{x + 10}" y="{y + 18}">{sg._esc(title)}</text>']
    for i, ln in enumerate(lines):
        out.append(f'<text class="bs" x="{x + 10}" y="{y + 34 + 13 * i}">{sg._esc(ln)}</text>')
    return "".join(out)


def _arrow(x1, y1, x2, y2, label="", lx=None, ly=None) -> str:
    out = [f'<path class="arrow" d="M {x1} {y1} L {x2} {y2}"/>']
    if label:
        out.append(f'<text class="bs" x="{lx if lx is not None else (x1 + x2) / 2}" '
                   f'y="{ly if ly is not None else (y1 + y2) / 2 - 4}" text-anchor="middle">{sg._esc(label)}</text>')
    return "".join(out)


def system_diagram() -> str:
    p = [_defs()]
    # host column
    p.append(_box(20, 16, 250, 118, "Windows host", [
        "watchdog: heartbeat kill, spend/disk stop,",
        "pause on battery / CPU load,",
        "git push rk-work + rk-findings",
        "config.json + configure.py + watcher"]))
    p.append(_box(20, 152, 250, 64, "credentials", [
        "GitHub PAT: host only, never mounted",
        "codex auth.json: mounted read-only"]))
    # container
    p.append(_box(320, 16, 300, 200, "run container (docker)", []))
    p.append(_box(336, 44, 268, 46, "rk-harness  (mounted :ro)", [
        "verifier + evaluator + cost models",
        "pinned sha256 checked at start"], hl=True))
    p.append(_box(336, 100, 128, 52, "runner", ["cycle loop", "only LLM caller"]))
    p.append(_box(480, 100, 124, 52, "search", ["CMA-ES islands", "enumeration"]))
    p.append(_box(336, 160, 268, 46, "rk-work  (mounted rw)", [
        "append-only archive, events, ledger"]))
    # outer services
    p.append(_box(670, 16, 240, 64, "Codex (plan)", [
        "directives + hypotheses + digests",
        "web search server-side"]))
    p.append(_box(670, 100, 240, 52, "rk-findings", ["auto site, rebuilt each cycle"]))
    p.append(_box(670, 168, 240, 48, "GitHub Pages", ["pages-build-deployment on push"]))
    p.append(_arrow(270, 75, 320, 75, "docker run"))
    p.append(_arrow(620, 60, 670, 48, "throttled calls"))
    p.append(_arrow(620, 126, 670, 126, "commit"))
    p.append(_arrow(270, 184, 336, 184, "push (host)", 300, 178))
    p.append(_arrow(790, 152, 790, 168, ""))
    svg = (f'<svg viewBox="0 0 930 236" width="930" height="236" role="img" '
           'aria-label="System diagram: host, container with read-only harness, and services">'
           + "".join(p) + "</svg>")
    return ('<figure class="panel"><figcaption>The as-built system. The verifier lives inside '
            "the read-only mount; the credential never crosses the container boundary."
            f'</figcaption><div class="scroll">{svg}</div>{_howto(T.HOW_SYSTEM)}</figure>')


def cycle_diagram() -> str:
    steps = [
        ("replay", "archive → state"),
        ("encourager", "ladder + calendar"),
        ("candidates", "enumerate / CMA-ES"),
        ("verify ×9", "pure code, exact"),
        ("evaluate", "Q15, 3 cost models"),
        ("tier", "vs cell incumbent"),
        ("append", "fsync JSONL"),
        ("ledger", "verdicts by code"),
        ("site", "regenerate + guard"),
        ("commit", "host pushes later"),
    ]
    p = [_defs()]
    bw, bh, gap = 168, 52, 18
    for i, (t, s) in enumerate(steps):
        row, col = divmod(i, 5)
        x = 16 + col * (bw + gap)
        y = 16 + row * (bh + 40)
        p.append(_box(x, y, bw, bh, t, [s], hl=(t == "verify ×9")))
        if col < 4:
            p.append(_arrow(x + bw, y + bh / 2, x + bw + gap, y + bh / 2))
    p.append(_arrow(16 + 4 * (bw + gap) + bw / 2, 16 + bh, 16 + bw / 2 + 8, 16 + bh + 40 - 2))
    svg = (f'<svg viewBox="0 0 950 210" width="950" height="210" role="img" '
           'aria-label="Cycle loop: replay, encourager, candidates, verify, evaluate, tier, append, ledger, site, commit">'
           + "".join(p) + "</svg>")
    return ('<figure class="panel"><figcaption>One idempotent cycle; a crash anywhere costs at most '
            f'one cycle.</figcaption><div class="scroll">{svg}</div>{_howto(T.HOW_CYCLE)}</figure>')


# ----------------------------------------------------------------------------- charts

def _linear_line(points: list[tuple[float, float]], w, h, xlabel, ylabel, aria) -> str:
    xlo, xhi = 0, max(x for x, _ in points) or 1
    ylo, yhi = 0, max(y for _, y in points) * 1.06 or 1
    ml, mr, mt, mb = 56, 14, 10, 34
    fx = lambda v: ml + (v - xlo) / (xhi - xlo) * (w - ml - mr)
    fy = lambda v: h - mb - (v - ylo) / (yhi - ylo) * (h - mt - mb)
    p = []
    for i in range(5):
        yv = ylo + (yhi - ylo) * i / 4
        p.append(f'<line class="gridline" x1="{ml}" y1="{sg._fmt(fy(yv))}" x2="{w - mr}" y2="{sg._fmt(fy(yv))}"/>')
        p.append(f'<text x="{ml - 6}" y="{sg._fmt(fy(yv) + 3.5)}" text-anchor="end">{int(yv)}</text>')
    for i in range(6):
        xv = xlo + (xhi - xlo) * i / 5
        p.append(f'<text x="{sg._fmt(fx(xv))}" y="{h - mb + 14}" text-anchor="middle">{int(xv)}</text>')
    p.append(f'<line class="axis" x1="{ml}" y1="{h - mb}" x2="{w - mr}" y2="{h - mb}"/>')
    path = " ".join(f"{'M' if i == 0 else 'L'} {sg._fmt(fx(x))} {sg._fmt(fy(y))}" for i, (x, y) in enumerate(points))
    p.append(f'<path d="{path}" fill="none" stroke="var(--s1)" stroke-width="2"/>')
    last = points[-1]
    p.append(f'<circle cx="{sg._fmt(fx(last[0]))}" cy="{sg._fmt(fy(last[1]))}" r="4" fill="var(--s1)" class="cellstroke">'
             f'<title>cycle {int(last[0])}: {int(last[1])} records</title></circle>')
    p.append(f'<text class="lbl" x="{sg._fmt(fx(last[0]) - 8)}" y="{sg._fmt(fy(last[1]) - 8)}" text-anchor="end">{int(last[1])}</text>')
    p.append(f'<text x="{sg._fmt((ml + w - mr) / 2)}" y="{h - 6}" text-anchor="middle">{sg._esc(xlabel)}</text>')
    p.append(f'<text x="12" y="{sg._fmt((mt + h - mb) / 2)}" text-anchor="middle" '
             f'transform="rotate(-90 12 {sg._fmt((mt + h - mb) / 2)})">{sg._esc(ylabel)}</text>')
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{sg._esc(aria)}">'
            + "".join(p) + "</svg>")


def records_chart(records) -> str:
    by_cycle = Counter(r.cycle_id for r in records)
    pts, total = [], 0
    for c in sorted(by_cycle):
        total += by_cycle[c]
        pts.append((float(c), float(total)))
    if not pts:
        return ""
    svg = _linear_line(pts, 620, 300, "cycle", "records (cumulative)",
                       "Cumulative archive records against cycle number")
    return ('<figure><figcaption>Archive growth. The jumps are the exhaustive phases; the flat '
            "stretch is the order-4 dry spell before the projection fallback landed."
            f"</figcaption>{svg}</figure>")


def _count_bars(counts: list[tuple[str, int]], w, aria, sw="var(--s1)") -> str:
    if not counts:
        return ""
    vmax = max(v for _k, v in counts)
    row_h, ml = 26, 168
    h = 12 + row_h * len(counts) + 8
    p = []
    for i, (k, v) in enumerate(counts):
        y = 8 + row_h * i
        bw = (v / vmax) * (w - ml - 70) if vmax else 0
        p.append(f'<text x="{ml - 6}" y="{sg._fmt(y + 13)}" text-anchor="end">{sg._esc(k)}</text>')
        p.append(f'<rect x="{ml}" y="{y}" width="{sg._fmt(max(bw, 2))}" height="18" rx="4" fill="{sw}" class="cellstroke">'
                 f'<title>{sg._esc(k)}: {v}</title></rect>')
        p.append(f'<text class="lbl" x="{sg._fmt(ml + max(bw, 2) + 6)}" y="{sg._fmt(y + 13)}">{v}</text>')
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{sg._esc(aria)}">'
            + "".join(p) + "</svg>")


def tier_chart(records) -> str:
    c = Counter(r.tier for r in records)
    rows = [(k, c.get(k, 0)) for k in ("heldout_verified", "search_only", "unreplicated")]
    return ('<figure><figcaption>Tier distribution over every archived record (assigned '
            "mechanically against each cell's incumbent)</figcaption>"
            + _count_bars(rows, 560, "Records per confidence tier") + "</figure>")


def reject_chart(events) -> str:
    c = Counter(e.get("code") for e in events if e.get("kind") == "rejected")
    rows = sorted(((str(k), v) for k, v in c.items()), key=lambda kv: -kv[1])
    if not rows:
        return ""
    return ('<figure><figcaption>Verifier rejections by code, whole run</figcaption>'
            + _count_bars(rows, 560, "Rejections per verifier code", sw="var(--s2)") + "</figure>")


def rounding_chart(data: dict) -> str:
    if not data:
        return ""
    search = ("dahlquist", "damped_osc", "vanderpol_mild")
    def rms(mode, method):
        vals = [data[mode][method][p] for p in search if isinstance(data[mode][method].get(p), (int, float))]
        return math.sqrt(sum(v * v for v in vals) / len(vals)) if vals else None
    methods = ["euler", "heun2", "rk4", "rk38"]
    w, h, ml, mb, mt = 620, 300, 56, 40, 14
    vals = {m: (rms("floor", m), rms("round_to_nearest", m)) for m in methods}
    vmax = max(v for pair in vals.values() for v in pair if v)
    plot_h = h - mb - mt
    scale = plot_h / (vmax * 1.2)
    group_w = (w - ml - 20) / len(methods)
    bar_w, gap = 52, 2
    p = [f'<line class="axis" x1="{ml}" y1="{h - mb}" x2="{w - 10}" y2="{h - mb}"/>']
    for gi, m in enumerate(methods):
        cx = ml + group_w * gi + group_w / 2
        for k, (label, v, sw) in enumerate((("floor (ASRS)", vals[m][0], "var(--s1)"),
                                            ("round-to-nearest", vals[m][1], "var(--s2)"))):
            if v is None:
                continue
            bx = cx - bar_w - gap / 2 + k * (bar_w + gap)
            bh = v * scale
            p.append(sg._round_top_bar(bx, h - mb - bh, bar_w, bh, sw,
                                       f"{m}, {label}: search-set RMS error {v:.4f}"))
            p.append(f'<text class="lbl" x="{sg._fmt(bx + bar_w / 2)}" y="{sg._fmt(h - mb - bh - 5)}" '
                     f'text-anchor="middle">{v:.3f}</text>')
        p.append(f'<text x="{sg._fmt(cx)}" y="{h - mb + 16}" text-anchor="middle">{sg._esc(m)}</text>')
    svg = (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
           'aria-label="Search-set RMS error under floor and round-to-nearest rounding, per method">'
           + "".join(p) + "</svg>")
    return ("<figure><figcaption>Rounding mode changes the ranking: under the mandated floor "
            "semantics Euler's bias-driven error undercuts rk4's; round-to-nearest restores the "
            "textbook ordering. Same budget (65,536 cycles, m0plus_fast), same problems."
            "</figcaption>"
            + sg._legend([("var(--s1)", "floor (as specified: ASRS semantics)"),
                          ("var(--s2)", "round-to-nearest (counterfactual)")]) + svg + "</figure>")


_TIER_MEANING = {
    "heldout_verified": "better than the cell incumbent on the search and held-out aggregates, "
                        "improving at least two problem families",
    "search_only": "better than the cell incumbent on the search aggregate but not on held-out",
    "unreplicated": "no incumbent to compare against, or no improvement on either aggregate",
}


def _phase0_body(t, rec, cyc: int) -> str:
    """The full archived score vector for one phase-0 point, shown when its row is expanded."""
    a21 = sg._frac(t.A[1][0])
    if rec is None:
        return (f'<p class="note">a21 = {a21}; enumerated at {cyc} slow cycles/step, but no '
                "archived record for this point at snapshot time.</p>")
    sv = rec.score
    # Unprefixed keys are the primary model's per-problem errors; "slow:" and "avr_approx:"
    # prefixes mark the advisory columns.
    per = [(k, v) for k, v in sorted(sv.per_problem.items()) if ":" not in k]
    per_txt = "; ".join(f"{sg._esc(n)} {sg._num(v)}" for n, v in per)
    cyc_txt = ", ".join(f"{m} {sg._num(sv.cycles.get(m))}"
                        for m in ("m0plus_fast", "m0plus_slow", "avr_approx"))
    pairs = [
        ("tableau", f"a21 = {a21}; b = ({sg._frac(t.b[0])}, {sg._frac(t.b[1])}); "
                    f"c = (0, {a21})"),
        ("cycles per step", cyc_txt),
        ("CSD weight total", sg._num(sv.csd_weight_total)),
        ("coefficient quantisation error", sg._num(sv.coeff_quant_error)),
        ("measured order", f"{sg._num(sv.measured_order)} from {sv.order_fit_points} fit points"),
        ("error constant", sg._num(sv.error_constant)),
        ("stability interval", f"real {sg._num(sv.stability_real)}, "
                               f"imaginary {sg._num(sv.stability_imag)}"),
        ("overflow margin", sg._num(sv.overflow_margin)),
        ("search error", sg._num(sv.search_error)),
        ("held-out error", sg._num(sv.heldout_error)),
        ("per-problem error (primary model)", per_txt or "n/a"),
        ("tier", f"{sg._tier_badge(rec.tier)} {sg._esc(_TIER_MEANING.get(rec.tier, ''))}"),
        ("archived", f"cycle {rec.cycle_id}, appended {sg._esc(timefmt.fmt_ct(rec.timestamp))}"),
        ("tableau hash", f'<span class="hash">{sg._esc(rec.tableau_hash)}</span>'),
    ]
    dl = "".join(f"<dt>{sg._esc(k)}</dt><dd>{v}</dd>" for k, v in pairs)
    return f'<dl class="meta">{dl}</dl>'


def phase0_rows(records) -> str:
    """The 16 phase-0 points as expandable rows: summary = the table columns, body = depth."""
    by_hash = {r.tableau_hash: r for r in records}
    names = {tableau_mod.content_hash(t): n for n, t in tableau_mod.classical().items()}
    parts = ['<div class="p0head"><span></span><span>a21</span><span>b</span>'
             "<span>slow cycles</span><span>held-out error</span><span>tier</span>"
             "<span></span></div>"]
    for cyc, t in enumeration.cheapest(enumeration.enumerate_phase0(), costmodel.M0PLUS_SLOW):
        h = tableau_mod.content_hash(t)
        rec = by_hash.get(h)
        parts.append(
            '<details class="p0"><summary>'
            f'<span class="mono">{sg._frac(t.A[1][0])}</span>'
            f'<span class="mono">({sg._frac(t.b[0])}, {sg._frac(t.b[1])})</span>'
            f"<span>{cyc}</span>"
            f"<span>{sg._num(rec.score.heldout_error) if rec else 'n/a'}</span>"
            f"<span>{sg._tier_badge(rec.tier) if rec else ''}</span>"
            f"<span>{sg._esc(names.get(h, ''))}</span></summary>"
            f'<div class="p0body">{_phase0_body(t, rec, cyc)}</div></details>')
    return '<div class="scroll"><div class="p0wrap">' + "".join(parts) + "</div></div>"


# ----------------------------------------------------------------------------- pages

def build() -> None:
    records = archive.read_all()
    events = []
    ev_path = (WS / "rk-work" / "events.jsonl")
    if ev_path.exists():
        for line in ev_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                ev = json.loads(line)
                if isinstance(ev, dict):
                    events.append(ev)
            except ValueError:
                pass
    fr = {}
    fr_path = HERE / "floor_round.json"
    if fr_path.exists():
        try:
            fr = json.loads(fr_path.read_text(encoding="utf-8"))
        except ValueError:
            fr = {}
    fals = None
    f_path = WS / "rk-work" / "falsification.json"
    if f_path.exists():
        try:
            fals = json.loads(f_path.read_text(encoding="utf-8"))
        except ValueError:
            fals = None

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    # ---------------- index
    body = ['<div class="hero">', T.INTRO, "</div>"]
    body.append("<h2>Headline measurements</h2>")
    body.append(T.HEADLINES)
    body.append('<div class="two">')
    body.append('<div class="panel">' + sg._anchor_bars() + "</div>")
    if fals and isinstance(fals.get("methods"), dict) and "rk4" in fals["methods"]:
        body.append('<div class="panel">' + sg._sweep_chart("rk4 on damped_osc (falsification run)",
                                                            fals["methods"]["rk4"]) + "</div>")
    body.append("</div>")
    body.append("<h2>Reading this site</h2>")
    body.append('<p><a href="architecture.html">Architecture</a> explains the system and its trust '
                'boundaries; <a href="methodology.html">methodology</a> walks the validation: the '
                'gate at container start, the pinned verifier hash, the test tiers, the pre-flight '
                'drills, and the watchdog; <a href="design-decisions.html">design decisions</a> '
                'records every deliberate choice and what happened to it in the build; '
                '<a href="results.html">results</a> carries the run-level charts; the '
                f'<a href="findings/index.html">findings snapshot ({SNAPSHOT_DATE})</a> is a frozen copy of '
                'the machine-generated site, and the <a href="https://jgoetzmann.github.io/rk-findings/">live '
                "findings site</a> keeps moving with the run.</p>")
    pages = {"index.html": _page("rk — quantization-aware Runge-Kutta search", "\n".join(body),
                                 "index.html",
                                 "What the project is, why it exists, and what it has measured so far.")}

    # ---------------- architecture
    head, rest = T.ARCH_SECTIONS.split("<h2>The cycle loop</h2>", 1)
    body = [system_diagram(), head, "<h2>The cycle loop</h2>", cycle_diagram(), rest]
    pages["architecture.html"] = _page("architecture", "\n".join(body), "architecture.html",
                                       "The as-built system: boundaries, loop, arithmetic, search, host layer.")

    # ---------------- methodology
    pages["methodology.html"] = _page("methodology", T.METHODOLOGY, "methodology.html",
                                      "How the harness earns its numbers: the start gate, the "
                                      "pinned hash, the drills, and the watchdog.")

    # ---------------- design decisions
    body = ['<p class="note">Each entry: the original decision from DESIGN.md (written before the '
            "build), and what the working system actually does. Tags mark whether contact with "
            "reality kept or changed it.</p>"]
    body.append(_howto(T.HOW_DECISIONS))
    body.append("<h3>Contents</h3>")
    body.append('<ul class="toc">' + "".join(
        f'<li><a href="#{slug}">{sg._esc(title)}</a></li>'
        for slug, title, _orig, _asbuilt in T.DECISIONS) + "</ul>")
    for slug, title, orig, asbuilt in T.DECISIONS:
        changed = any(w in asbuilt.lower() for w in ("superseded", "amended", "changed"))
        tag = ('<span class="tag tag-changed">revised in build</span>' if changed
               else '<span class="tag tag-kept">held up</span>')
        body.append(f'<div class="decision" id="{slug}">'
                    f'<h3><a href="#{slug}" style="color:inherit;text-decoration:none">'
                    f"{sg._esc(title)}</a>{tag}</h3>"
                    f'<div class="orig"><strong>Original:</strong> {sg._esc(orig)}</div>'
                    f'<div class="asbuilt"><strong>As built:</strong> {sg._esc(asbuilt)}</div>'
                    "</div>")
    body.append("<h2>What was deliberately cut</h2>")
    body.append(T.CUTS)
    body.append("<h2>Known prior art, and where the gap is</h2>")
    body.append(T.PRIOR_ART)
    pages["design-decisions.html"] = _page("design decisions", "\n".join(body), "design-decisions.html",
                                           "Every deliberate choice, annotated with what the build did to it.")

    # ---------------- results
    body = ['<p class="note">Charts computed from the archive and event stream at snapshot time '
            f"({SNAPSHOT_DATE}, US Central); the live equivalents keep moving on rk-findings.</p>"]
    if records:
        last_ts = max(r.timestamp for r in records)
        body.append(f'<p class="note">Archive at this snapshot: {len(records):,} records; the '
                    f"latest was appended {sg._esc(timefmt.fmt_ct(last_ts))}.</p>")
    body.append(_panel(records_chart(records), T.HOW_RECORDS))
    body.append('<div class="two">')
    body.append(_panel(tier_chart(records), T.HOW_TIERS))
    body.append(_panel(reject_chart(events), T.HOW_REJECTS))
    body.append("</div>")
    body.append("<h2>The rounding experiment</h2>")
    body.append(_panel(rounding_chart(fr), T.HOW_ROUNDING))
    body.append("<h2>Phase 0, in full: the sixteen-point proof</h2>")
    body.append('<p class="note">The complete 2-stage order-2 space with exactly representable '
                "coefficients, cheapest to dearest under the slow multiplier. This is an "
                "enumeration, so the ordering is a proof within the space, not a search result. "
                "Click any row for the full archived record.</p>")
    body.append(_howto(T.HOW_PHASE0))
    body.append(phase0_rows(records))
    if fals and isinstance(fals.get("methods"), dict):
        body.append("<h2>Falsification sweeps</h2>")
        body.append(sg._legend([("var(--s1)", "Q15 fixed point"), ("var(--s2)", "float64, same steps")]))
        body.append(_howto(T.HOW_SWEEPS))
        body.append('<div class="charts">')
        for name in sorted(fals["methods"]):
            chart = sg._sweep_chart(name, fals["methods"][name])
            if chart:
                body.append('<div class="panel">' + chart + "</div>")
        body.append("</div>")
    pages["results.html"] = _page("results", "\n".join(body), "results.html",
                                  "Run-level charts the findings site does not carry.")

    for name, text in pages.items():
        (DOCS / name).write_text(text, encoding="utf-8")
        print("wrote", name, f"({len(text) // 1024} KB)")

    # ---------------- findings snapshot
    src = WS / "rk-findings" / "docs"
    dst = DOCS / "findings"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    print(f"snapshot: {len(list(dst.glob('*.html')))} findings pages copied")


if __name__ == "__main__":
    import os
    os.environ.setdefault("RK_WORK_DIR", str(WS / "rk-work"))
    build()
