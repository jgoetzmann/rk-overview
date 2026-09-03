"""Build the rk-overview site into docs/.

Snapshot semantics: run by hand, reads the live rk-work archive plus
tools/key_findings.json (written by tools/key_findings.py), copies the current
rk-findings pages under docs/findings/, and writes five authored pages. Reuses the
findings site's style tokens and a few chart primitives so the two sites read as one
system. Timezone policy: stored data is UTC; anything rendered for humans goes through
rk_harness.timefmt (US Central), and SNAPSHOT_DATE is a Central-time date.

    set PYTHONPATH=..\\rk-harness  (and RK_WORK_DIR to ..\\rk-work)
    python tools/generate.py
"""
from __future__ import annotations

import json
import math
import re
import shutil
import statistics
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent            # rk-overview/
WS = ROOT.parent              # workspace
sys.path.insert(0, str(WS / "rk-harness"))
sys.path.insert(0, str(HERE))

import pages_text as T  # noqa: E402
from rk_harness import archive, sitegen as sg  # noqa: E402
from rk_harness import coeffrep, costmodel, enumeration  # noqa: E402
from rk_harness import tableau as tableau_mod  # noqa: E402
from rk_harness import timefmt  # noqa: E402

SNAPSHOT_DATE = "2026-09-02"   # the date the snapshot was taken, US Central
DOCS = ROOT / "docs"
LIVE_URL = "https://jgoetzmann.github.io/rk-findings/"

# Test-suite figures, stated on the methodology page. Verified 2026-09-02 against
# `pytest --collect-only -q` in rk-harness across the twelve tier files
# and docs/REVIEW-REPORT.md item A3+ ("55 passed ... deselected"; the gate selection
# G1-G20 + K1 + K2 is fixed and does not grow with the suite).
TESTS_TOTAL = 1093
GATE_TESTS = 55
SUITE_TIERS = [
    ("T1", 332, "fixed point, coefficient representation, cycle counting"),
    ("T2", 216, "order conditions, evaluator, verifier"),
    ("T3", 234, "archive, search, directive validation"),
    ("T4", 184, "ledger, runner, site generator, epoch panel"),
    ("T5", 10, "operational config and the watch view"),
    ("T6", 8, "Central-time display formatting"),
    ("T7", 15, "the findings methodology page"),
    ("T8", 59, "the practical validation suite, stiff subset included"),
    ("T9", 8, "the epoch saturation orchestrator"),
    ("T10", 15, "the library benchmark harness"),
    ("T11", 6, "the adaptive embedded-pair prototype"),
    ("T12", 6, "the SDIRK implicit prototype"),
]
assert sum(n for _t, n, _c in SUITE_TIERS) == TESTS_TOTAL

# Pre-flight report figures, from rk-harness docs/REVIEW-REPORT.md (2026-08-30 run):
# 91 PASS, 0 FAIL, 8 MANUAL, 1 INFO, 0 SKIP; all twelve sections green.

# Decisions whose plan changed on contact with the build (tagged on the page).
REVISED_DECISIONS = {"credentials", "numbers-not-claims"}

# Page-specific components only. All shared chrome (font stack, heading scale, nav,
# footer, tables, figures, details/summary, palette tokens) comes from sitegen._STYLE
# unchanged, so the two sites read as siblings; never re-style what the base defines.
_EXTRA_STYLE = """
.herolead{font-size:17.5px;line-height:1.6;max-width:74ch}
.chips{display:flex;flex-wrap:wrap;gap:10px;margin:20px 0 8px}
.chip{background:var(--surface-1);border:1px solid var(--line);border-radius:10px;
  padding:10px 16px;min-width:120px}
.chip .v{font-size:22px;font-weight:650;font-variant-numeric:tabular-nums;
  letter-spacing:-.01em}
.chip .k{font-size:12px;color:var(--text-2)}
.grid-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));
  gap:14px;margin:16px 0}
a.gcard{display:block;background:var(--surface-1);border:1px solid var(--line);
  border-radius:12px;padding:14px 18px;text-decoration:none;color:inherit}
a.gcard:hover{border-color:var(--s1)}
a.gcard .t{font-weight:650;color:var(--s1);margin:0 0 4px;font-size:15px}
a.gcard .d{font-size:13px;color:var(--text-2)}
.teasers{margin:12px 0}
a.tease{display:grid;grid-template-columns:34px 1fr;gap:12px;align-items:baseline;
  padding:10px 14px;margin:8px 0;background:var(--surface-1);border:1px solid var(--line);
  border-radius:10px;text-decoration:none;color:inherit}
a.tease:hover{border-color:var(--s1)}
a.tease .tn{display:inline-grid;place-items:center;width:26px;height:26px;
  border-radius:8px;background:var(--s1);color:#fff;font-weight:700;font-size:14px}
a.tease .tt{font-weight:650}
a.tease .td{font-size:13px;color:var(--text-2)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start}
@media (max-width:900px){.two{grid-template-columns:1fr}}
p.verdict{font-size:17px;line-height:1.65;max-width:82ch}
section.finding{margin:44px 0;scroll-margin-top:16px}
section.finding h2{font-size:20px;margin-bottom:8px}
.findnum{display:inline-grid;place-items:center;width:30px;height:30px;border-radius:9px;
  background:var(--s1);color:#fff;font-size:16px;font-weight:700;margin-right:12px;
  vertical-align:-7px}
figure .src{display:block;margin-top:6px;font-size:12px;color:var(--text-3)}
svg text{font-size:13px}
svg .lbl{font-size:13px}
svg .dlab{font-weight:600;fill:var(--text-1);paint-order:stroke;stroke:var(--surface-1);
  stroke-width:3.5px;stroke-linejoin:round}
svg .bt{font-weight:650;fill:var(--text-1);font-size:15px}
svg .bs{fill:var(--text-2);font-size:14px}
svg .alab{font-size:12.5px;fill:var(--text-3);paint-order:stroke;stroke:var(--surface-1);stroke-width:3px;stroke-linejoin:round}
svg .box{fill:var(--surface-1);stroke:var(--line)}
svg .boxhl{fill:var(--surface-0);stroke:var(--s1);stroke-width:1.5}
svg .boxbad{fill:var(--bad-bg);stroke:var(--bad-fg)}
svg .frozen{stroke-dasharray:6 4}
svg .arrow{stroke:var(--text-3);fill:none;marker-end:url(#ah);stroke-width:1.5}
svg .arrowdash{stroke-dasharray:6 4}
svg .enclosure{fill:none;stroke:var(--text-3);stroke-dasharray:4 4;opacity:.7}
svg a text{fill:var(--s1)}
ol.checks li{margin:6px 0;max-width:82ch}
ul.toc{columns:2;column-gap:32px;font-size:13.5px;margin:8px 0 4px;padding-left:20px}
ul.toc li{margin:3px 0}
@media (max-width:700px){ul.toc{columns:1}}
.decision{background:var(--surface-1);border:1px solid var(--line);border-radius:10px;
  padding:16px 20px;margin:14px 0;scroll-margin-top:16px}
.decision:target{border-color:var(--s1)}
.decision h3{margin:0 0 6px;font-size:15px;color:var(--text-1)}
.decision .orig{color:var(--text-2);border-left:3px solid var(--line);padding-left:12px;
  margin:8px 0}
.decision .asbuilt{margin:8px 0 0}
.decision .tag{display:inline-block;padding:1px 8px;border-radius:99px;font-size:11px;
  font-weight:600;margin-left:8px;vertical-align:2px}
.tag-kept{background:var(--good-bg);color:var(--good-fg)}
.tag-changed{background:var(--warn-bg);color:var(--warn-fg)}
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
    ("results.html", "key findings"),
    ("tradeoffs.html", "trade-offs"),
    ("tracks.html", "research tracks"),
    ("methodology.html", "methodology"),
    ("architecture.html", "architecture"),
    ("design-decisions.html", "design decisions"),
    ("findings/index.html", f"findings snapshot ({SNAPSHOT_DATE})"),
)


def _nav(active: str) -> str:
    links = "".join(
        f'<a href="{href}"{" class=" + chr(34) + "on" + chr(34) if href == active else ""}>{sg._esc(label)}</a>'
        for href, label in _NAV)
    links += f'<a href="{LIVE_URL}">live findings ↗</a>'
    return f'<nav class="tabs">{links}</nav>'


def _page(title: str, body: str, active: str, subtitle: str = "") -> str:
    sub = f'<p class="sub">{sg._esc(subtitle)}</p>' if subtitle else ""
    footer = T.FOOTER.format(date=SNAPSHOT_DATE)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{sg._esc(title)}</title>\n"
        f"<style>{sg._STYLE}{_EXTRA_STYLE}</style>\n</head>\n<body>\n"
        '<header class="site"><div class="wrap">\n'
        f"<h1>{sg._esc(title)}</h1>\n{sub}\n"
        f"{_nav(active)}\n"
        "</div></header>\n"
        '<div class="wrap">\n'
        f"{body}\n"
        f"<footer>{sg._esc(footer)}</footer>\n"
        "</div>\n</body>\n</html>\n"
    )


def _panel(inner: str) -> str:
    if not inner:
        return ""
    return '<div class="panel">' + inner + "</div>"


def _fig(svg: str, caption_html: str, legend: str = "", source: str = "") -> str:
    """A key-findings figure, caption-first like the findings site's charts."""
    if not svg:
        return ""
    src = f'<span class="src">{sg._esc(source)}</span>' if source else ""
    return (f'<figure class="panel"><figcaption>{caption_html}{src}</figcaption>'
            + legend + f'<div class="scroll">{svg}</div></figure>')


def _short(v: float) -> str:
    return f"{v:.3g}"


# ----------------------------------------------------------------------------- diagrams
# Boxes are sized from their content: ~8.6 px/char for 15px semibold titles and
# ~7.35 px/char for 14px body lines, plus padding, so labels never overflow.

_TCH, _LCH = 8.6, 7.35


def _natw(title: str, lines: list[str], pad: int = 26) -> int:
    widths = [len(title) * _TCH] + [len(ln) * _LCH for ln in lines]
    return int(max(widths) + pad)


def _nath(lines: list[str]) -> int:
    return 40 if not lines else 44 + 19 * len(lines)


def _defs() -> str:
    return ('<defs><marker id="ah" markerWidth="9" markerHeight="9" refX="8" refY="4.5" '
            'orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="var(--text-3)"/></marker></defs>')


def _box(x, y, w, title, lines, cls="box", extra_cls="") -> str:
    h = _nath(lines)
    c = f"{cls} {extra_cls}".strip()
    out = [f'<rect class="{c}" x="{x}" y="{y}" width="{w}" height="{h}" rx="9"/>',
           f'<text class="bt" x="{x + 13}" y="{y + 23}">{sg._esc(title)}</text>']
    for i, ln in enumerate(lines):
        out.append(f'<text class="bs" x="{x + 13}" y="{y + 45 + 19 * i}">{sg._esc(ln)}</text>')
    return "".join(out)


def _arrow(x1, y1, x2, y2, label="", lx=None, ly=None, dashed=False) -> str:
    cls = "arrow arrowdash" if dashed else "arrow"
    out = [f'<path class="{cls}" d="M {x1} {y1} L {x2} {y2}"/>']
    if label:
        out.append(f'<text class="alab" x="{lx if lx is not None else (x1 + x2) / 2}" '
                   f'y="{ly if ly is not None else (y1 + y2) / 2 - 6}" '
                   f'text-anchor="middle">{sg._esc(label)}</text>')
    return "".join(out)


def _badge(x, y, text, bg, fg) -> str:
    w = len(text) * 7 + 14
    return (f'<rect x="{x}" y="{y}" width="{w}" height="19" rx="9" fill="{bg}"/>'
            f'<text x="{x + w / 2}" y="{y + 13.5}" text-anchor="middle" '
            f'style="font-size:11px;font-weight:700;fill:{fg}">{sg._esc(text)}</text>')


def repo_diagram() -> str:
    """The four-repository split, with the live/frozen cue for the two sites."""
    b1t, b1l = "rk-harness", ["the scorer: verifier, evaluator,",
                              f"cost models, {TESTS_TOTAL:,} tests",
                              "read-only in the container"]
    b2t, b2l = "rk-work", ["run state: append-only archive,",
                           "events, hypothesis ledger",
                           "the one writable mount"]
    b3t, b3l = "rk-findings", ["machine-generated numbers site,",
                               "rebuilt by the run every cycle"]
    b4t, b4l = "rk-overview  (this site)", ["human-written explainer pages",
                                            "+ a frozen copy of the findings site"]
    lab_a, lab_b = "verifies + scores", "rebuilt every cycle"
    w1, w2 = _natw(b1t, b1l), _natw(b2t, b2l)
    # widest of the two right boxes, with room for the corner badge beside the title
    w3 = max(_natw(b3t, b3l), _natw(b4t, b4l), int(len(b4t) * _TCH) + 13 + 76 + 18)
    gap_a = int(len(lab_a) * 6.4) + 26   # arrow gaps sized to their labels
    gap_b = int(len(lab_b) * 6.4) + 26
    x1, y1 = 20, 46
    x2 = x1 + w1 + gap_a
    x3 = x2 + w2 + gap_b
    h1, h2, h3, h4 = _nath(b1l), _nath(b2l), _nath(b3l), _nath(b4l)
    y4 = y1 + h3 + 88
    W = x3 + w3 + 20
    H = y4 + h4 + 62
    p = [_defs()]
    # container enclosure around the two mounted repos
    p.append(f'<rect class="enclosure" x="{x1 - 10}" y="{y1 - 26}" '
             f'width="{x2 + w2 - x1 + 20}" height="{max(h1, h2) + 40}" rx="12"/>')
    p.append(f'<text class="alab" x="{x1 - 2}" y="{y1 - 32}">mounted into the run container</text>')
    p.append(_box(x1, y1, w1, b1t, b1l, cls="boxhl"))
    p.append(_box(x2, y1, w2, b2t, b2l))
    p.append(_box(x3, y1, w3, b3t, b3l))
    p.append(_badge(x3 + w3 - 58, y1 + 10, "LIVE", "var(--good-bg)", "var(--good-fg)"))
    p.append(_box(x3, y4, w3, b4t, b4l, extra_cls="frozen"))
    p.append(_badge(x3 + w3 - 76, y4 + 10, "FROZEN", "var(--mut-bg)", "var(--mut-fg)"))
    p.append(_arrow(x1 + w1, y1 + h1 / 2, x2, y1 + h2 / 2, lab_a))
    p.append(_arrow(x2 + w2, y1 + h2 / 2, x3, y1 + h3 / 2, lab_b))
    p.append(f'<path class="arrow arrowdash" d="M {x3 + w3 / 2} {y1 + h3} L {x3 + w3 / 2} {y4}"/>')
    p.append(f'<text class="alab" x="{x3 + w3 / 2 - 12}" y="{(y1 + h3 + y4) / 2 + 4}" '
             f'text-anchor="end">frozen copy taken {SNAPSHOT_DATE}</text>')
    p.append(f'<a href="{LIVE_URL}"><text class="alab" x="{x3}" y="{y1 + h3 + 18}" '
             f'style="fill:var(--s1)">jgoetzmann.github.io/rk-findings ↗ (live)</text></a>')
    p.append(f'<text class="alab" x="{x3}" y="{y4 + h4 + 18}">jgoetzmann.github.io/rk-overview</text>')
    p.append(f'<text class="alab" x="{x3}" y="{y4 + h4 + 34}">(you are here, frozen at {SNAPSHOT_DATE})</text>')
    svg = (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
           'aria-label="The four repositories: rk-harness and rk-work mounted into the '
           'container, rk-findings rebuilt every cycle and published live, rk-overview a '
           'frozen snapshot">' + "".join(p) + "</svg>")
    return ('<figure class="panel"><figcaption>One writer and one trust level per '
            "repository: boxes are git repositories, the dashed enclosure is the container "
            "boundary, and the dashed arrow is the one-time snapshot copy. The live site "
            "keeps moving with the run; this site is a dated snapshot.</figcaption>"
            f'<div class="scroll">{svg}</div></figure>')


def system_diagram() -> str:
    hostt = "Windows host"
    hostl = ["watchdog: heartbeat kill,",
             "spend / disk stop, battery pause,",
             "git pushes + config + watcher"]
    credt = "credentials"
    credl = ["GitHub PAT: host only, not mounted",
             "Codex auth: mounted read-only"]
    harnt = "rk-harness  (read-only mount)"
    harnl = ["verifier + evaluator + cost models", "sha256 pinned, checked at start"]
    runt, runl = "runner", ["cycle loop; the only LLM caller"]
    seat, seal = "search", ["CMA-ES islands + enumeration"]
    workt = "rk-work  (writable mount)"
    workl = ["append-only archive, events, ledger"]
    cxt, cxl = "Codex (planning)", ["directives, hypotheses, digests"]
    fint, finl = "rk-findings", ["auto site, rebuilt every cycle"]
    pgt, pgl = "GitHub Pages", ["deploys on push from the host"]

    c1w = max(_natw(hostt, hostl), _natw(credt, credl))
    iw = max(_natw(harnt, harnl), _natw(workt, workl),
             _natw(runt, runl) + 12 + _natw(seat, seal))
    c2w = iw + 32
    c3w = max(_natw(cxt, cxl), _natw(fint, finl), _natw(pgt, pgl))
    lab_run, lab_push = "docker run", "git push (host)"
    lab_llm, lab_commit = "throttled LLM calls", "commit each cycle"
    gap1 = max(96, int(max(len(lab_run), len(lab_push)) * 6.4) + 26)
    gap2 = max(96, int(max(len(lab_llm), len(lab_commit)) * 6.4) + 26)
    x1, x2 = 16, 16 + c1w + gap1
    x3 = x2 + c2w + gap2
    W = x3 + c3w + 16

    p = [_defs()]
    y = 16
    p.append(_box(x1, y, c1w, hostt, hostl))
    hosth = _nath(hostl)
    p.append(_box(x1, y + hosth + 18, c1w, credt, credl))
    # container: outer box drawn manually so inner boxes stack inside it
    ih_harn, ih_run, ih_work = _nath(harnl), _nath(runl), _nath(workl)
    inner_y = y + 36
    cont_h = 36 + ih_harn + 12 + ih_run + 12 + ih_work + 16
    p.append(f'<rect class="box" x="{x2}" y="{y}" width="{c2w}" height="{cont_h}" rx="10"/>')
    p.append(f'<text class="bt" x="{x2 + 13}" y="{y + 24}">run container (docker)</text>')
    p.append(_box(x2 + 16, inner_y, iw, harnt, harnl, cls="boxhl"))
    ry = inner_y + ih_harn + 12
    rw = _natw(runt, runl)
    p.append(_box(x2 + 16, ry, rw, runt, runl))
    p.append(_box(x2 + 16 + rw + 12, ry, iw - rw - 12, seat, seal))
    wy = ry + ih_run + 12
    p.append(_box(x2 + 16, wy, iw, workt, workl))
    # right column
    cxh, finh = _nath(cxl), _nath(finl)
    y_cx = 16
    y_fin = y_cx + cxh + 26
    y_pg = y_fin + finh + 26
    p.append(_box(x3, y_cx, c3w, cxt, cxl))
    p.append(_box(x3, y_fin, c3w, fint, finl))
    p.append(_box(x3, y_pg, c3w, pgt, pgl))
    # arrows
    p.append(_arrow(x1 + c1w, y + 44, x2, y + 44, lab_run))
    p.append(_arrow(x1 + c1w, y + hosth + 60, x2, wy + 20, lab_push,
                    lx=x1 + c1w + gap1 / 2, ly=(y + hosth + 60 + wy + 20) / 2 - 10))
    p.append(_arrow(x2 + c2w, ry + ih_run / 2, x3, y_cx + cxh / 2, lab_llm,
                    lx=x2 + c2w + gap2 / 2, ly=(ry + ih_run / 2 + y_cx + cxh / 2) / 2 - 10))
    p.append(_arrow(x2 + c2w, wy + 20, x3, y_fin + finh / 2, lab_commit,
                    lx=x2 + c2w + gap2 / 2, ly=(wy + 20 + y_fin + finh / 2) / 2 - 10))
    p.append(_arrow(x3 + c3w / 2, y_fin + finh, x3 + c3w / 2, y_pg))
    H = max(y + cont_h, y_pg + _nath(pgl)) + 16
    svg = (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
           'aria-label="System diagram: host, container with read-only harness, and services">'
           + "".join(p) + "</svg>")
    return ('<figure class="panel"><figcaption>The as-built system, three columns left to '
            "right: the Windows host, the docker container, and the services the run talks "
            "to. The verifier lives inside the read-only mount, and no arrow carries the "
            "GitHub credential across the container boundary.</figcaption>"
            f'<div class="scroll">{svg}</div></figure>')


def cycle_diagram() -> str:
    steps = [
        ("replay", "archive → state"),
        ("encourager", "ladder + calendar"),
        ("candidates", "enumerate / CMA-ES"),
        ("verify ×9", "nine checks, exact"),
        ("evaluate", "Q15, 3 cost models"),
        ("tier", "vs cell incumbent"),
        ("append", "fsync JSONL"),
        ("ledger", "verdicts by code"),
        ("site", "rebuild + guard"),
        ("commit", "host pushes later"),
    ]
    bw = max(_natw(t, [s]) for t, s in steps)
    bh = _nath(["x"])
    gap, row_gap = 44, 52
    p = [_defs()]
    for i, (t, s) in enumerate(steps):
        row, col = divmod(i, 5)
        x = 16 + col * (bw + gap)
        y = 16 + row * (bh + row_gap)
        p.append(_box(x, y, bw, t, [s], cls="boxhl" if t.startswith("verify") else "box"))
        if col < 4:
            p.append(_arrow(x + bw, y + bh / 2, x + bw + gap, y + bh / 2))
    # wrap arrow from the end of row 1 down and back to the start of row 2
    x_last = 16 + 4 * (bw + gap)
    y2 = 16 + bh + row_gap
    p.append(f'<path class="arrow" d="M {x_last + bw / 2} {16 + bh} '
             f'L {x_last + bw / 2} {16 + bh + row_gap / 2} '
             f'L {16 + bw / 2} {16 + bh + row_gap / 2} L {16 + bw / 2} {y2 - 2}"/>')
    W = 16 * 2 + 5 * bw + 4 * gap
    H = 16 * 2 + 2 * bh + row_gap
    svg = (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
           'aria-label="Cycle loop: replay, encourager, candidates, verify, evaluate, '
           'tier, append, ledger, site, commit">' + "".join(p) + "</svg>")
    return ('<figure class="panel"><figcaption>One idempotent cycle, read left to right, '
            "top row then bottom. Replay rebuilds all state from the append-only archive "
            "and nothing before the fsynced append has side effects, so a crash anywhere "
            "costs at most one cycle.</figcaption>"
            f'<div class="scroll">{svg}</div></figure>')


def pipeline_diagram() -> str:
    """The container start gate, in execution order, with the exit-1 branch."""
    chain = [
        ("container start", []),
        ("1 · write heartbeat", ["the first line of the entrypoint"]),
        ("2 · read-only probe", ["a write to /harness must fail"]),
        ("3 · verifier hash check", ["sha256 over ten files vs the pinned value"]),
        ("4 · golden + canary tests", [f"{GATE_TESTS} cases with pytest, under four seconds"]),
        ("runner starts", ["science on a proven environment only"]),
    ]
    failt = "exit 1"
    faill = ["the runner never starts;", "the watchdog restarts, the gate re-runs"]
    cw = max(_natw(t, ls) for t, ls in chain)
    fw = _natw(failt, faill)
    gap_y = 30
    x, y = 16, 16
    fx = x + cw + 96
    p = [_defs()]
    ys = []
    for t, ls in chain:
        h = _nath(ls)
        hl = t == "runner starts"
        p.append(_box(x, y, cw, t, ls, cls="boxhl" if hl else "box"))
        ys.append((y, h))
        y += h + gap_y
    for (by, bh), (ny, _nh) in zip(ys, ys[1:]):
        p.append(_arrow(x + cw / 2, by + bh, x + cw / 2, ny - 2))
    # exit-1 branch: a rail collecting the four checks
    fail_top = ys[1][0]
    fail_bot = ys[4][0] + ys[4][1]
    fh = _nath(faill)
    fy = (fail_top + fail_bot) / 2 - fh / 2
    railx = x + cw + 46
    p.append(f'<rect class="boxbad" x="{fx}" y="{fy}" width="{fw}" height="{fh}" rx="9"/>')
    p.append(f'<text x="{fx + 13}" y="{fy + 23}" style="font-weight:650;font-size:15px;'
             f'fill:var(--bad-fg)">{failt}</text>')
    for i, ln in enumerate(faill):
        p.append(f'<text x="{fx + 13}" y="{fy + 45 + 19 * i}" style="font-size:14px;'
                 f'fill:var(--bad-fg)">{sg._esc(ln)}</text>')
    for by, bh in ys[1:5]:
        p.append(f'<path d="M {x + cw} {by + bh / 2} L {railx} {by + bh / 2}" '
                 'stroke="var(--bad-fg)" fill="none" opacity=".55"/>')
    p.append(f'<path d="M {railx} {ys[1][0] + ys[1][1] / 2} L {railx} {fy + fh / 2}" '
             'stroke="var(--bad-fg)" fill="none" opacity=".55"/>')
    p.append(f'<path d="M {railx} {fy + fh / 2} L {fx - 2} {fy + fh / 2}" '
             'stroke="var(--bad-fg)" fill="none" marker-end="url(#ah)"/>')
    p.append(f'<text class="alab" x="{railx - 6}" y="{ys[1][0] + 8}" '
             'text-anchor="end" style="fill:var(--bad-fg)">any failure</text>')
    W = fx + fw + 16
    H = y - gap_y + 16
    svg = (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
           'aria-label="Start gate: heartbeat, read-only probe, hash check, golden and '
           'canary tests, then the runner; any failure exits">' + "".join(p) + "</svg>")
    return ('<figure class="panel"><figcaption>The start gate, run on every container '
            "start, in execution order top to bottom. The runner is unreachable until all "
            "four checks pass against the harness as mounted; any failure takes the exit-1 "
            "branch, and the gate re-runs on the next start.</figcaption>"
            f'<div class="scroll">{svg}</div></figure>')


# ----------------------------------------------------------------------------- key-findings charts

def _kf_load() -> dict:
    path = HERE / "key_findings.json"
    if not path.exists():
        print("WARN: key_findings.json missing; findings charts skipped")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        print("WARN: key_findings.json unparsable; findings charts skipped")
        return {}


def _series(kf: dict, finding: str, name: str):
    s = kf.get(finding, {}).get("series", {}).get(name)
    if isinstance(s, list) and s:
        return s
    if isinstance(s, dict) and s and "absent" not in s:
        return s
    print(f"WARN: series {finding}.{name} empty or absent; chart skipped")
    return None


def _logpos(v, lo, hi, a, b) -> float:
    t = (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))
    return a + t * (b - a)


def _tickfmt(v: float) -> str:
    return f"{v:g}"


def frontier_chart(kf: dict) -> str:
    rows = _series(kf, "efficiency", "frontier_cycles_vs_heldout")
    if not rows:
        return ""
    w, h, ml, mr, mt, mb = 880, 470, 66, 26, 18, 52
    xlo, xhi, ylo, yhi = 4, 95, 0.02, 0.45
    fx = lambda v: _logpos(v, xlo, xhi, ml, w - mr)
    fy = lambda v: h - mb - (_logpos(v, ylo, yhi, 0, h - mt - mb))
    p = []
    for tv in (5, 10, 20, 40, 80):
        p.append(f'<line class="gridline" x1="{sg._fmt(fx(tv))}" y1="{mt}" x2="{sg._fmt(fx(tv))}" y2="{h - mb}"/>')
        p.append(f'<text x="{sg._fmt(fx(tv))}" y="{h - mb + 18}" text-anchor="middle">{tv}</text>')
    for tv in (0.02, 0.05, 0.1, 0.2, 0.4):
        p.append(f'<line class="gridline" x1="{ml}" y1="{sg._fmt(fy(tv))}" x2="{w - mr}" y2="{sg._fmt(fy(tv))}"/>')
        p.append(f'<text x="{ml - 8}" y="{sg._fmt(fy(tv) + 4)}" text-anchor="end">{_tickfmt(tv)}</text>')
    p.append(f'<line class="axis" x1="{ml}" y1="{h - mb}" x2="{w - mr}" y2="{h - mb}"/>')
    p.append(f'<line class="axis" x1="{ml}" y1="{mt}" x2="{ml}" y2="{h - mb}"/>')
    p.append(f'<text x="{sg._fmt((ml + w - mr) / 2)}" y="{h - 8}" text-anchor="middle">cycles per step (log)</text>')
    p.append(f'<text x="14" y="{sg._fmt((mt + h - mb) / 2)}" text-anchor="middle" '
             f'transform="rotate(-90 14 {sg._fmt((mt + h - mb) / 2)})">held-out error (log)</text>')
    classical = [r for r in rows if r.get("kind") == "classical"]
    discovered = [r for r in rows if r.get("kind") == "discovered"]
    best_classical = min((r["heldout_error"] for r in classical), default=None)
    if best_classical:
        yy = fy(best_classical)
        p.append(f'<line x1="{ml}" y1="{sg._fmt(yy)}" x2="{w - mr}" y2="{sg._fmt(yy)}" '
                 'stroke="var(--s2)" stroke-dasharray="5 4" opacity=".7"/>')
        p.append(f'<text class="dlab" x="{w - mr - 4}" y="{sg._fmt(yy - 7)}" text-anchor="end">'
                 f'best classical anchor ({_short(best_classical)})</text>')
    for i, r in enumerate(sorted(classical, key=lambda r: r["cycles"])):
        px, py = fx(r["cycles"]), fy(r["heldout_error"])
        p.append(f'<circle cx="{sg._fmt(px)}" cy="{sg._fmt(py)}" r="5.5" fill="var(--s2)" class="cellstroke">'
                 f'<title>{sg._esc(r.get("name"))} (classical): {r["cycles"]} cycles/step, '
                 f'held-out error {_short(r["heldout_error"])}</title></circle>')
        dy = -10 if i % 2 == 0 else 20
        p.append(f'<text class="dlab" x="{sg._fmt(px)}" y="{sg._fmt(py + dy)}" '
                 f'text-anchor="middle">{sg._esc(r.get("name"))}</text>')
    best = min(discovered, key=lambda r: r["heldout_error"], default=None)
    for r in discovered:
        px, py = fx(r["cycles"]), fy(r["heldout_error"])
        p.append(f'<circle cx="{sg._fmt(px)}" cy="{sg._fmt(py)}" r="5.5" fill="var(--s1)" class="cellstroke">'
                 f'<title>discovered, order {r.get("order")}, {r.get("stages")} stages: '
                 f'{r["cycles"]} cycles/step, held-out error {_short(r["heldout_error"])}, '
                 f'tier {sg._esc(r.get("tier"))}</title></circle>')
    if best:
        px, py = fx(best["cycles"]), fy(best["heldout_error"])
        p.append(f'<circle cx="{sg._fmt(px)}" cy="{sg._fmt(py)}" r="10" fill="none" '
                 'stroke="var(--s1)" stroke-width="1.5"/>')
        p.append(f'<text class="dlab" x="{sg._fmt(px + 14)}" y="{sg._fmt(py + 4)}">'
                 f'best discovered: {_short(best["heldout_error"])} at {best["cycles"]} cycles</text>')
    svg = (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
           'aria-label="Efficiency frontier: per-step cycles against held-out error, '
           'discovered versus classical methods, both axes log">' + "".join(p) + "</svg>")
    caption = ("Each dot is one method at the shared 65,536-cycle budget: x is per-step "
               "cost in cycles, y is held-out error, both log, so down and left is "
               "better. Orange dots are the eight classical anchors, named; blue dots "
               "are the best archived method in each occupied grid cell. Every blue dot "
               "below the dashed line beats every classical anchor outright. Hover any "
               "dot for its cell and tier.")
    legend = sg._legend([("var(--s1)", "discovered (best per grid cell)"),
                         ("var(--s2)", "classical anchors")])
    return _fig(svg, caption, legend, "data: key_findings.json, series frontier_cycles_vs_heldout")


def flip_slope_chart(kf: dict) -> str:
    agg = kf.get("floor_bias_flip", {}).get("numbers", {}).get("aggregate", {})
    try:
        fl = agg["floor"]["search_rms"]
        rd = agg["round_to_nearest"]["search_rms"]
    except KeyError:
        print("WARN: floor_bias_flip aggregate numbers missing; slope chart skipped")
        return ""
    methods = sorted(fl["rank"], key=lambda m: fl["rank"][m])
    w, h = 660, 330
    xr, xf = 218, 452
    y0, dy = 92, 62
    colors = {"euler": "var(--s1)", "rk4": "var(--s2)"}
    p = [f'<text class="dlab" x="{xr}" y="40" text-anchor="middle">round-to-nearest</text>',
         f'<text class="alab" x="{xr}" y="56" text-anchor="middle">(counterfactual)</text>',
         f'<text class="dlab" x="{xf}" y="40" text-anchor="middle">floor (ASRS)</text>',
         f'<text class="alab" x="{xf}" y="56" text-anchor="middle">(what the hardware does)</text>']
    for rank in range(1, 5):
        p.append(f'<text x="40" y="{y0 + (rank - 1) * dy + 4}" text-anchor="middle">rank {rank}</text>')
    for m in methods:
        yr = y0 + (rd["rank"][m] - 1) * dy
        yf = y0 + (fl["rank"][m] - 1) * dy
        c = colors.get(m, "var(--text-3)")
        p.append(f'<path d="M {xr} {yr} L {xf} {yf}" stroke="{c}" stroke-width="2.5" fill="none" '
                 f'opacity="{1 if m in colors else 0.65}"/>')
        for (xx, yy) in ((xr, yr), (xf, yf)):
            p.append(f'<circle cx="{xx}" cy="{yy}" r="5" fill="{c}" class="cellstroke">'
                     f'<title>{sg._esc(m)}: search-set RMS {_short(rd["error"][m])} under '
                     f'round-to-nearest, {_short(fl["error"][m])} under floor</title></circle>')
        p.append(f'<text class="dlab" x="{xr - 14}" y="{yr + 4}" text-anchor="end">'
                 f'{sg._esc(m)} · {_short(rd["error"][m])}</text>')
        p.append(f'<text class="dlab" x="{xf + 14}" y="{yf + 4}">'
                 f'{sg._esc(m)} · {_short(fl["error"][m])}</text>')
    svg = (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
           'aria-label="Rank slope chart: method ranking by search-set RMS error under '
           'round-to-nearest versus floor rounding">' + "".join(p) + "</svg>")
    caption = ("Each line is one method; its ends are the method's rank by search-set "
               "RMS error under the two rounding modes, with the RMS value beside each "
               "end. Blue and orange mark the extreme movers, euler and rk4; the gray "
               "methods swap too (heun2 4th to 2nd, rk38 1st to 3rd). Floor is what the "
               "harness measures everywhere; round-to-nearest was rerun outside the "
               "archive as the counterfactual.")
    return _fig(svg, caption, "", "data: key_findings.json, numbers aggregate.search_rms")


_PROBLEM_ORDER = ("dahlquist", "damped_osc", "vanderpol_mild",
                  "pendulum", "dc_motor", "rc_thermal", "quaternion")
_METHOD_ORDER = ("euler", "heun2", "rk4", "rk38")


def flip_problem_chart(kf: dict) -> str:
    rows = _series(kf, "floor_bias_flip", "per_problem_floor_vs_round")
    if not rows:
        return ""
    by = {(r["problem"], r["method"]): r for r in rows}
    w, ml, mr = 880, 160, 26
    xlo, xhi = 3e-5, 1.0
    fx = lambda v: _logpos(v, xlo, xhi, ml, w - mr)
    head_h, row_h, group_pad = 24, 22, 14
    problems = [pr for pr in _PROBLEM_ORDER if any(k[0] == pr for k in by)]
    H = 16 + sum(head_h + row_h * len(_METHOD_ORDER) + group_pad for _ in problems) + 34
    p = []
    for tv in (1e-4, 1e-3, 1e-2, 1e-1, 1):
        px = fx(tv)
        p.append(f'<line class="gridline" x1="{sg._fmt(px)}" y1="10" x2="{sg._fmt(px)}" y2="{H - 30}"/>')
        p.append(f'<text x="{sg._fmt(px)}" y="{H - 12}" text-anchor="middle">{sg._pow_label(tv)}</text>')
    y = 16
    for pr in problems:
        p.append(f'<text class="dlab" x="8" y="{y + 14}">{sg._esc(pr)}</text>')
        y += head_h
        for m in _METHOD_ORDER:
            r = by.get((pr, m))
            if r is None:
                continue
            cy = y + row_h / 2
            fxv, rxv = fx(r["floor_error"]), fx(r["round_error"])
            p.append(f'<text x="{ml - 10}" y="{sg._fmt(cy + 4)}" text-anchor="end">{sg._esc(m)}</text>')
            p.append(f'<line x1="{sg._fmt(min(fxv, rxv))}" y1="{sg._fmt(cy)}" '
                     f'x2="{sg._fmt(max(fxv, rxv))}" y2="{sg._fmt(cy)}" stroke="var(--line)" stroke-width="2"/>')
            title = (f"{pr} / {m}: floor {_short(r['floor_error'])} (rank {r['floor_rank']}), "
                     f"round-to-nearest {_short(r['round_error'])} (rank {r['round_rank']})")
            p.append(f'<circle cx="{sg._fmt(fxv)}" cy="{sg._fmt(cy)}" r="4.5" fill="var(--s1)" '
                     f'class="cellstroke"><title>{sg._esc(title)}</title></circle>')
            p.append(f'<circle cx="{sg._fmt(rxv)}" cy="{sg._fmt(cy)}" r="4.5" fill="var(--s2)" '
                     f'class="cellstroke"><title>{sg._esc(title)}</title></circle>')
            y += row_h
        y += group_pad
    svg = (f'<svg viewBox="0 0 {w} {H}" width="{w}" height="{H}" role="img" '
           'aria-label="Per-problem error under floor and round-to-nearest for four '
           'classical methods, log scale">' + "".join(p) + "</svg>")
    caption = ("One row per problem and method; the x axis is final-state error on a log "
               "scale, so left is better. The blue dot is the error under floor, the "
               "orange dot under round-to-nearest, and the connecting bar is what the "
               "rounding mode alone changes. On dahlquist the three cheap methods' floor "
               "dots sit at 4.5e-5, the reference value itself, two decades left of "
               "their round-to-nearest dots. Hover a dot for exact values and ranks.")
    legend = sg._legend([("var(--s1)", "floor (ASRS, as measured)"),
                         ("var(--s2)", "round-to-nearest (counterfactual)")])
    return _fig(svg, caption, legend, "data: key_findings.json, series per_problem_floor_vs_round")


def crossover_chart(kf: dict) -> str:
    sweeps = _series(kf, "crossover", "sweeps")
    if not sweeps:
        return ""
    methods = kf.get("crossover", {}).get("numbers", {}).get("methods", {})
    w, h, ml, mr, mt, mb = 880, 480, 70, 36, 44, 52
    xlo, xhi, ylo, yhi = 0.008, 1.6, 1e-11, 1e2
    fx = lambda v: _logpos(v, xlo, xhi, ml, w - mr)
    fy = lambda v: h - mb - _logpos(v, ylo, yhi, 0, h - mt - mb)
    p = []
    for tv in (0.01, 0.05, 0.1, 0.5, 1):
        p.append(f'<line class="gridline" x1="{sg._fmt(fx(tv))}" y1="{mt}" x2="{sg._fmt(fx(tv))}" y2="{h - mb}"/>')
        p.append(f'<text x="{sg._fmt(fx(tv))}" y="{h - mb + 18}" text-anchor="middle">{_tickfmt(tv)}</text>')
    for e in range(-10, 3, 2):
        tv = 10.0 ** e
        p.append(f'<line class="gridline" x1="{ml}" y1="{sg._fmt(fy(tv))}" x2="{w - mr}" y2="{sg._fmt(fy(tv))}"/>')
        p.append(f'<text x="{ml - 8}" y="{sg._fmt(fy(tv) + 4)}" text-anchor="end">1e{e}</text>')
    p.append(f'<line class="axis" x1="{ml}" y1="{h - mb}" x2="{w - mr}" y2="{h - mb}"/>')
    p.append(f'<line class="axis" x1="{ml}" y1="{mt}" x2="{ml}" y2="{h - mb}"/>')
    p.append(f'<text x="{sg._fmt((ml + w - mr) / 2)}" y="{h - 8}" text-anchor="middle">step size h (log; smaller steps to the left)</text>')
    p.append(f'<text x="14" y="{sg._fmt((mt + h - mb) / 2)}" text-anchor="middle" '
             f'transform="rotate(-90 14 {sg._fmt((mt + h - mb) / 2)})">final-state error (log)</text>')
    colors = {"rk4": "var(--s1)", "heun2": "var(--s2)"}
    for li, (mname, cross_label_y) in enumerate((("rk4", mt + 14), ("heun2", mt + 30))):
        cross = methods.get(mname, {}).get("crossover_h")
        if isinstance(cross, (int, float)) and xlo < cross < xhi:
            px = fx(cross)
            p.append(f'<line x1="{sg._fmt(px)}" y1="{mt}" x2="{sg._fmt(px)}" y2="{h - mb}" '
                     'stroke="var(--text-3)" stroke-dasharray="4 3"/>')
            p.append(f'<text class="dlab" x="{sg._fmt(px + 5)}" y="{cross_label_y}">'
                     f'{sg._esc(mname)} crossover h = {_short(cross)}</text>')
    for mname in ("rk4", "heun2"):
        rows = [r for r in sweeps.get(mname, []) if r.get("h") and r["h"] <= 1.3]
        c = colors[mname]
        for key, dash in (("q15_error", ""), ("float_error", ' stroke-dasharray="6 4"')):
            pts = [(r["h"], r[key]) for r in rows
                   if isinstance(r.get(key), (int, float)) and ylo <= r[key] <= yhi]
            if len(pts) < 2:
                continue
            pts.sort()
            path = " ".join(f"{'M' if i == 0 else 'L'} {sg._fmt(fx(hv))} {sg._fmt(fy(ev))}"
                            for i, (hv, ev) in enumerate(pts))
            p.append(f'<path d="{path}" fill="none" stroke="{c}" stroke-width="2"{dash}/>')
            for hv, ev in pts:
                p.append(f'<circle cx="{sg._fmt(fx(hv))}" cy="{sg._fmt(fy(ev))}" r="3.5" fill="{c}" '
                         f'class="cellstroke"><title>{sg._esc(mname)} '
                         f'{"Q15" if key == "q15_error" else "float64"} at h = {_short(hv)}: '
                         f'error {_short(ev)}</title></circle>')
            if key == "float_error":
                # one direct label per method, at the left end of its float64 line,
                # where the two methods sit five decades apart
                h0, e0 = pts[0]
                p.append(f'<text class="dlab" x="{sg._fmt(fx(h0) + 10)}" '
                         f'y="{sg._fmt(fy(e0) - 8)}">{sg._esc(mname)}</text>')
    svg = (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
           'aria-label="Step-size sweep on damped_osc: Q15 and float64 error for rk4 and '
           'heun2, log-log, with crossover markers">' + "".join(p) + "</svg>")
    caption = ("Final-state error on damped_osc against step size, both axes log, one "
               "color per method: solid lines are Q15 fixed point, dashed lines are "
               "float64 taking exactly the same steps, so the vertical gap is pure "
               "arithmetic. Left of each dashed vertical, the Q15 line detaches and "
               "climbs while the float line keeps falling. Q15 points at h ≥ 1.25 "
               "overflowed (error infinite) and are omitted.")
    legend = sg._legend([("var(--s1)", "rk4 (solid Q15, dashed float64)"),
                         ("var(--s2)", "heun2 (solid Q15, dashed float64)")])
    return _fig(svg, caption, legend, "data: key_findings.json, series sweeps (falsification run)")


_RC_ORDER = ("euler", "midpoint", "heun2", "ralston2", "heun3", "kutta3", "rk4", "rk38")


def rc_chart(kf: dict) -> str:
    rows = _series(kf, "rc_thermal_collapse", "per_method")
    if not rows:
        return ""
    nums = kf.get("rc_thermal_collapse", {}).get("numbers", {})
    ref = nums.get("reference_norm")
    best = nums.get("best_discovered_rc_thermal", {})
    by = {r["method"]: r for r in rows}
    order = [m for m in _RC_ORDER if m in by]
    groups = [(m, by[m]) for m in order] + ([("best discovered", None)] if best else [])
    w, h, ml, mr, mt, mb = 880, 400, 64, 20, 24, 66
    ymax = 0.22
    fy = lambda v: h - mb - (v / ymax) * (h - mt - mb)
    p = []
    for tv in (0, 0.05, 0.10, 0.15, 0.20):
        p.append(f'<line class="gridline" x1="{ml}" y1="{sg._fmt(fy(tv))}" x2="{w - mr}" y2="{sg._fmt(fy(tv))}"/>')
        p.append(f'<text x="{ml - 8}" y="{sg._fmt(fy(tv) + 4)}" text-anchor="end">{_tickfmt(tv)}</text>')
    p.append(f'<line class="axis" x1="{ml}" y1="{h - mb}" x2="{w - mr}" y2="{h - mb}"/>')
    gw = (w - ml - mr) / len(groups)
    bar_w, gap = 26, 4
    for gi, (name, r) in enumerate(groups):
        cx = ml + gw * gi + gw / 2
        if r is not None:
            fe, re_ = r["floor_error"], r.get("round_error")
            bx = cx - (bar_w + gap / 2 if re_ is not None else bar_w / 2)
            p.append(sg._round_top_bar(bx, fy(fe), bar_w, (h - mb) - fy(fe), "var(--s1)",
                                       f"{name} floor: error {_short(fe)}; {r['steps']:,} steps; "
                                       f"final Q15 state {tuple(r['final_state_q15'])}"))
            if re_ is not None:
                bx2 = cx + gap / 2
                p.append(sg._round_top_bar(bx2, fy(re_), bar_w, (h - mb) - fy(re_), "var(--s2)",
                                           f"{name} round-to-nearest: error {_short(re_)}"))
                if name in ("rk38", "rk4"):
                    p.append(f'<text class="lbl" x="{sg._fmt(bx2 + bar_w / 2)}" '
                             f'y="{sg._fmt(fy(re_) - 5)}" text-anchor="middle">{_short(re_)}</text>')
        else:
            bx = cx - bar_w / 2
            fe = best["error"]
            p.append(sg._round_top_bar(bx, fy(fe), bar_w, (h - mb) - fy(fe), "var(--s3)",
                                       f"best discovered (order {best.get('order')}, "
                                       f"{best.get('stages')} stages, {best.get('cycles')} cycles/step), "
                                       f"still under floor: error {_short(fe)}"))
            p.append(f'<text class="lbl" x="{sg._fmt(cx)}" y="{sg._fmt(fy(fe) - 5)}" '
                     f'text-anchor="middle">{_short(fe)}</text>')
        if name == "best discovered":
            p.append(f'<text x="{sg._fmt(cx)}" y="{h - mb + 18}" text-anchor="middle">best</text>')
            p.append(f'<text x="{sg._fmt(cx)}" y="{h - mb + 34}" text-anchor="middle">discovered</text>')
        else:
            p.append(f'<text x="{sg._fmt(cx)}" y="{h - mb + 18}" text-anchor="middle">{sg._esc(name)}</text>')
    if isinstance(ref, (int, float)):
        p.append(f'<line x1="{ml}" y1="{sg._fmt(fy(ref))}" x2="{w - mr}" y2="{sg._fmt(fy(ref))}" '
                 'stroke="var(--text-1)" stroke-dasharray="5 4" opacity=".6"/>')
        p.append(f'<text class="dlab" x="{w - mr - 4}" y="{sg._fmt(fy(ref) - 7)}" text-anchor="end">'
                 f'true solution norm {_short(ref)}</text>')
    p.append(f'<text class="dlab" x="{ml + 6}" y="{sg._fmt(fy(0.156) + 22)}">'
             'floor: 0.156–0.158 for all eight</text>')
    svg = (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
           'aria-label="rc_thermal error per method under floor and round-to-nearest, '
           'with the reference norm marked">' + "".join(p) + "</svg>")
    caption = ("Final-state error on rc_thermal per method. Blue bars (floor) all reach "
               "the dashed line: the state collapsed to near zero, so the reported error "
               "is the size of the true solution itself. Orange bars are the "
               "round-to-nearest counterfactual, measured for four methods. The green "
               "bar is the best discovered method, which stays well under the line while "
               "using the same floor arithmetic. Hover a bar for steps and final state.")
    legend = sg._legend([("var(--s1)", "floor (ASRS, as measured)"),
                         ("var(--s2)", "round-to-nearest (counterfactual)"),
                         ("var(--s3)", "best discovered, still under floor")])
    return _fig(svg, caption, legend, "data: key_findings.json, series per_method")


def phase0_chart(kf: dict) -> str:
    rows = _series(kf, "phase0_exhaustive", "all_members")
    if not rows:
        return ""
    def a21val(r):
        return float(Fraction(r["a21"]))
    rows = sorted(rows, key=a21val)
    w, h, ml, mr, mt, mb = 880, 380, 64, 20, 24, 58
    ylo, yhi = 0.05, 0.145
    fy = lambda v: h - mb - (v - ylo) / (yhi - ylo) * (h - mt - mb)
    slot = (w - ml - mr) / len(rows)
    p = []
    for tv in (0.06, 0.08, 0.10, 0.12, 0.14):
        p.append(f'<line class="gridline" x1="{ml}" y1="{sg._fmt(fy(tv))}" x2="{w - mr}" y2="{sg._fmt(fy(tv))}"/>')
        p.append(f'<text x="{ml - 8}" y="{sg._fmt(fy(tv) + 4)}" text-anchor="end">{_tickfmt(tv)}</text>')
    p.append(f'<line class="axis" x1="{ml}" y1="{h - mb}" x2="{w - mr}" y2="{h - mb}"/>')
    p.append(f'<text x="{sg._fmt((ml + w - mr) / 2)}" y="{h - 8}" text-anchor="middle">'
             'a21, ordered by value (each dot is one of the 16 exactly representable tableaus)</text>')
    for i, r in enumerate(rows):
        cx = ml + slot * i + slot / 2
        cy = fy(r["heldout_error"])
        named = r.get("name")
        fill = "var(--s1)" if r["rank"] == 1 else ("var(--s2)" if named else "var(--text-3)")
        title = (f"a21 = {r['a21']}, b = ({r['b'][0]}, {r['b'][1]}): held-out error "
                 f"{_short(r['heldout_error'])}, {r['cycles']} cycles/step, rank {r['rank']} of 16"
                 + (f" ({named})" if named else ""))
        p.append(f'<circle cx="{sg._fmt(cx)}" cy="{sg._fmt(cy)}" r="6" fill="{fill}" class="cellstroke">'
                 f'<title>{sg._esc(title)}</title></circle>')
        if r["rank"] == 1:
            p.append(f'<circle cx="{sg._fmt(cx)}" cy="{sg._fmt(cy)}" r="11" fill="none" '
                     'stroke="var(--s1)" stroke-width="1.5"/>')
            p.append(f'<text class="dlab" x="{sg._fmt(cx)}" y="{sg._fmt(cy - 18)}" '
                     f'text-anchor="middle">optimum {_short(r["heldout_error"])}</text>')
        elif r["rank"] == 2:
            p.append(f'<text class="dlab" x="{sg._fmt(cx)}" y="{sg._fmt(cy + 26)}" '
                     f'text-anchor="middle">near-tie {_short(r["heldout_error"])}</text>')
        elif named:
            dy = -12 if named == "heun2" else 22
            p.append(f'<text class="dlab" x="{sg._fmt(cx)}" y="{sg._fmt(cy + dy)}" '
                     f'text-anchor="middle">{sg._esc(named)}</text>')
        p.append(f'<text x="{sg._fmt(cx)}" y="{h - mb + 18}" text-anchor="middle" '
                 f'class="mono" style="font-size:12px">{sg._esc(r["a21"])}</text>')
    svg = (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
           'aria-label="Phase 0 exhaustive: held-out error for all sixteen 2-stage '
           'order-2 tableaus, ordered by a21">' + "".join(p) + "</svg>")
    caption = ("All sixteen members of the phase-0 space, ordered by a21; y is held-out "
               "error at the shared budget (linear, lower is better). Blue is the "
               "optimum, orange marks the two members that are textbook methods, gray is "
               "everything else. Because the space was enumerated in full, the blue dot "
               "is a proof, not a sample. Hover a dot for its b weights and rank.")
    return _fig(svg, caption, "", "data: key_findings.json, series all_members")


def _validation_load() -> dict:
    path = WS / "rk-work" / "validation" / "results.json"
    if not path.exists():
        print("WARN: validation results.json missing; validation chart skipped")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        print("WARN: validation results.json unparsable; validation chart skipped")
        return {}


def validation_chart(vd: dict) -> str:
    """Dumbbell per practical problem: best classical vs best discovered Q15 error.
    Scoped to the non-stiff problems; the stiff subset is a different story (overflow,
    not accuracy) and lives on the trade-offs and tracks pages."""
    per = (vd.get("verdicts") or {}).get("per_problem") or {}
    order = [p.get("name") for p in vd.get("problems", []) if p.get("name") in per]
    order += sorted(k for k in per if k not in set(order))
    rows = [(name, per[name]) for name in order
            if not per[name].get("stiff")
            and isinstance(per[name].get("best_classical_q15_error"), (int, float))
            and isinstance(per[name].get("best_discovered_q15_error"), (int, float))]
    if not rows:
        print("WARN: validation per-problem verdicts empty; chart skipped")
        return ""
    vals = [v for _n, d in rows for v in (d["best_classical_q15_error"],
                                          d["best_discovered_q15_error"])]
    w, ml, mr = 880, 150, 30
    xlo = 10 ** math.floor(math.log10(min(vals)))
    xhi = 10 ** math.ceil(math.log10(max(vals)))
    fx = lambda v: _logpos(v, xlo, xhi, ml, w - mr)
    row_h = 56
    H = 16 + row_h * len(rows) + 36
    p = []
    tv = xlo
    while tv <= xhi * 1.0001:
        px = fx(tv)
        p.append(f'<line class="gridline" x1="{sg._fmt(px)}" y1="10" x2="{sg._fmt(px)}" y2="{H - 32}"/>')
        p.append(f'<text x="{sg._fmt(px)}" y="{H - 14}" text-anchor="middle">{sg._pow_label(tv)}</text>')
        tv *= 10
    for i, (name, d) in enumerate(rows):
        cy = 16 + row_h * i + row_h / 2
        cx_c, cx_d = fx(d["best_classical_q15_error"]), fx(d["best_discovered_q15_error"])
        p.append(f'<text class="dlab" x="{ml - 12}" y="{sg._fmt(cy + 4)}" text-anchor="end">{sg._esc(name)}</text>')
        p.append(f'<line x1="{sg._fmt(min(cx_c, cx_d))}" y1="{sg._fmt(cy)}" '
                 f'x2="{sg._fmt(max(cx_c, cx_d))}" y2="{sg._fmt(cy)}" stroke="var(--line)" stroke-width="3"/>')
        ratio = d.get("ratio_discovered_over_classical")
        title = (f"{name}: best classical {d.get('best_classical')} at "
                 f"{_short(d['best_classical_q15_error'])}, best discovered at "
                 f"{_short(d['best_discovered_q15_error'])}"
                 + (f" (ratio {_short(ratio)})" if isinstance(ratio, (int, float)) else ""))
        p.append(f'<circle cx="{sg._fmt(cx_c)}" cy="{sg._fmt(cy)}" r="6.5" fill="var(--s2)" '
                 f'class="cellstroke"><title>{sg._esc(title)}</title></circle>')
        p.append(f'<circle cx="{sg._fmt(cx_d)}" cy="{sg._fmt(cy)}" r="6.5" fill="var(--s1)" '
                 f'class="cellstroke"><title>{sg._esc(title)}</title></circle>')
        lab_c = f"{sg._esc(str(d.get('best_classical')))} {_short(d['best_classical_q15_error'])}"
        lab_d = _short(d["best_discovered_q15_error"])
        if cx_d <= cx_c:   # discovered wins: its label to the left, classical's to the right
            sides = ((cx_d, cy, lab_d, "left"), (cx_c, cy, lab_c, "right"))
        else:
            sides = ((cx_c, cy, lab_c, "left"), (cx_d, cy, lab_d, "right"))
        for cx, yy, lab, side in sides:
            est = len(lab) * 7.3   # ~13px semibold advance width, conservative
            if side == "left" and cx - 11 - est >= ml - 6:
                p.append(f'<text class="dlab" x="{sg._fmt(cx - 11)}" y="{sg._fmt(yy + 4)}" '
                         f'text-anchor="end">{lab}</text>')
            elif side == "right" and cx + 11 + est <= w - 6:
                p.append(f'<text class="dlab" x="{sg._fmt(cx + 11)}" y="{sg._fmt(yy + 4)}">{lab}</text>')
            else:   # no horizontal room: sit the label above its dot instead
                p.append(f'<text class="dlab" x="{sg._fmt(cx)}" y="{sg._fmt(yy - 13)}" '
                         f'text-anchor="middle">{lab}</text>')
    svg = (f'<svg viewBox="0 0 {w} {H}" width="{w}" height="{H}" role="img" '
           'aria-label="Best classical versus best discovered Q15 error on each practical '
           'validation problem, log scale">' + "".join(p) + "</svg>")
    wins = [n for n, d in rows
            if d["best_discovered_q15_error"] < d["best_classical_q15_error"]]
    losses = [n for n, _d in rows if n not in wins]
    tail = (f"; on {', '.join(losses)} the classical anchor keeps the win"
            if losses else "")
    caption = ("One row per practical problem; x is final-state Q15 error at the shared "
               "65,536-cycle budget, log scale, so left is better. The orange dot is the "
               "best classical anchor (named, with its error), the blue dot the best "
               "discovered method, and the bar between them is the gap. Blue sits left "
               f"(discovered wins) on {len(wins)} of the {len(rows)} rows{tail}. "
               "Hover a row for exact values and the error ratio.")
    legend = sg._legend([("var(--s1)", "best discovered"),
                         ("var(--s2)", "best classical anchor")])
    return _fig(svg, caption, legend, "data: rk-work/validation/results.json, verdicts.per_problem")


# ----------------------------------------------------------------------------- tracks page

def _json_file(path: Path, label: str) -> dict:
    if not path.exists():
        print(f"WARN: {label} missing; section skipped")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        print(f"WARN: {label} unparsable; section skipped")
        return {}


def orchestrator_panel() -> str:
    """The same progress-loop state the findings epoch panel shows, read through
    sitegen.epoch_status_data() so the two sites cannot disagree."""
    d = sg.epoch_status_data()
    state = d.get("state", "active")
    badge = f'<span class="badge badge-{sg._esc(state)}">{sg._esc(state)}</span>'
    rows = []
    if state == "frozen":
        rows.append(("frozen at", sg._esc(timefmt.fmt_ct(d.get("frozen_at")))))
        if d.get("freeze_reason"):
            rows.append(("reason", sg._esc(str(d.get("freeze_reason")))))
    if d.get("last_progress_ts") and d.get("last_progress_kind"):
        rows.append(("last progress",
                     f"{sg._esc(timefmt.fmt_ct(d.get('last_progress_ts')))} "
                     f"({sg._esc(str(d.get('last_progress_kind')))})"))
    else:
        rows.append(("last progress", "no progress events recorded yet"))
    rows.append(("saturation counter",
                 f"{d.get('consecutive')} consecutive saturating checks; "
                 f"{d.get('consecutive_needed')} trigger a freeze"))
    if d.get("last_check_ts"):
        rows.append(("last check", sg._esc(timefmt.fmt_ct(d.get("last_check_ts")))
                     + (f", verdict {sg._esc(str(d.get('last_verdict')))}"
                        if d.get("last_verdict") else "")))
    rows.append(("falsification file",
                 "present" if d.get("falsification_present") else "not yet produced"))
    dl = '<dl class="meta">' + "".join(
        f"<dt>{sg._esc(k)}</dt><dd>{v}</dd>" for k, v in rows) + "</dl>"
    head = (f'<p style="margin:0 0 6px"><strong>Epoch {d.get("epoch")}</strong> {badge} '
            '<span class="when">scored method class: explicit fixed-step '
            "Runge-Kutta</span></p>")
    return '<div class="panel">' + head + dl + "</div>"


_ADAPTIVE_COLORS = {"buck_converter": "var(--s1)", "pll_lock": "var(--s2)",
                    "glucose_minimal": "var(--s3)"}


def adaptive_curve_chart(ac: dict) -> str:
    pts = [p for p in (ac.get("points") or [])
           if isinstance(p.get("n_fevals"), int) and isinstance(p.get("achieved_error"), (int, float))
           and p["achieved_error"] > 0]
    if not pts:
        print("WARN: adaptive_curve points empty; chart skipped")
        return ""
    xs = [p["n_fevals"] for p in pts]
    ys = [p["achieved_error"] for p in pts]
    xlo = 10 ** math.floor(math.log10(min(xs)))
    xhi = 10 ** math.ceil(math.log10(max(xs)))
    ylo = 10 ** math.floor(math.log10(min(ys)))
    yhi = 10 ** math.ceil(math.log10(max(ys)))
    pl = sg._LogLog(680, 400, xlo, xhi, ylo, yhi,
                    "function evaluations (log)", "achieved error (log)", ml=64)
    pl.frame()
    problems = [pr for pr in _ADAPTIVE_COLORS if any(p["problem"] == pr for p in pts)]
    problems += sorted({p["problem"] for p in pts} - set(problems))
    for pr in problems:
        rows = sorted((p for p in pts if p["problem"] == pr), key=lambda p: p["n_fevals"])
        c = _ADAPTIVE_COLORS.get(pr, "var(--text-3)")
        path = " ".join(f"{'M' if i == 0 else 'L'} {sg._fmt(pl.x(p['n_fevals']))} "
                        f"{sg._fmt(pl.y(p['achieved_error']))}" for i, p in enumerate(rows))
        pl.parts.append(f'<path d="{path}" fill="none" stroke="{c}" stroke-width="2"/>')
        for p in rows:
            title = (f"{pr} at tol {p.get('tol')}: {p['n_fevals']} fevals, achieved error "
                     f"{_short(p['achieved_error'])}, {p.get('n_rejected')} rejected steps")
            pl.parts.append(f'<circle cx="{sg._fmt(pl.x(p["n_fevals"]))}" '
                            f'cy="{sg._fmt(pl.y(p["achieved_error"]))}" r="4" fill="{c}" '
                            f'class="cellstroke"><title>{sg._esc(title)}</title></circle>')
        last = rows[-1]
        pl.parts.append(f'<text class="dlab" x="{sg._fmt(pl.x(last["n_fevals"]) - 8)}" '
                        f'y="{sg._fmt(pl.y(last["achieved_error"]) - 10)}" '
                        f'text-anchor="end">{sg._esc(pr)}</text>')
    svg = pl.svg("Work-precision curve of the Bogacki-Shampine 3(2) prototype: achieved "
                 "error against function evaluations on three validation problems")
    caption = ("Measured work-precision behavior of the float64 Bogacki–Shampine 3(2) "
               "prototype with the dyadic PI controller: each line is one validation "
               "problem, each dot one run at a requested tolerance from 1e-3 down to 1e-8, "
               "x is right-hand-side evaluations and y is the error actually achieved, "
               "both log. Error falling in lockstep with tolerance at single-digit "
               "rejection counts is the behavior the epoch-2 controller needs. "
               "Preliminary and float-only: no Q15 effects are modeled.")
    legend = sg._legend([(v, k) for k, v in _ADAPTIVE_COLORS.items()])
    return _fig(svg, caption, legend, "data: rk-work/prototypes/adaptive_curve.json, points")


_SDIRK_COLORS = {"sdirk2": "var(--s1)", "rk4": "var(--s2)", "euler": "var(--text-3)"}


def sdirk_chart(sc: dict) -> str:
    prob = (sc.get("problems") or {}).get("stiff_two_rate") or {}
    methods = prob.get("methods") or {}
    if not methods:
        print("WARN: sdirk_curve stiff_two_rate missing; chart skipped")
        return ""
    series: dict[str, list[tuple[float, float]]] = {}
    for name, m in methods.items():
        cyc = m.get("est_cycles_per_step")
        pts = [(p["n"] * cyc, p["error"]) for p in (m.get("points") or [])
               if p.get("status") == "ok" and isinstance(p.get("error"), (int, float))
               and p["error"] > 0]
        if pts:
            series[name] = sorted(pts)
    if not series:
        return ""
    w, h, ml, mr, mt, mb = 680, 420, 74, 20, 26, 52
    xlo, xhi = 1e3, 4e6
    ylo, yhi = 1e-16, 1e1
    fx = lambda v: _logpos(v, xlo, xhi, ml, w - mr)
    fy = lambda v: h - mb - _logpos(v, ylo, yhi, 0, h - mt - mb)
    p = []
    for e in (3, 4, 5, 6):
        tv = 10.0 ** e
        p.append(f'<line class="gridline" x1="{sg._fmt(fx(tv))}" y1="{mt}" x2="{sg._fmt(fx(tv))}" y2="{h - mb}"/>')
        p.append(f'<text x="{sg._fmt(fx(tv))}" y="{h - mb + 18}" text-anchor="middle">1e{e}</text>')
    for e in range(-16, 2, 4):
        tv = 10.0 ** e
        p.append(f'<line class="gridline" x1="{ml}" y1="{sg._fmt(fy(tv))}" x2="{w - mr}" y2="{sg._fmt(fy(tv))}"/>')
        p.append(f'<text x="{ml - 8}" y="{sg._fmt(fy(tv) + 4)}" text-anchor="end">1e{e}</text>')
    p.append(f'<line class="axis" x1="{ml}" y1="{h - mb}" x2="{w - mr}" y2="{h - mb}"/>')
    p.append(f'<line class="axis" x1="{ml}" y1="{mt}" x2="{ml}" y2="{h - mb}"/>')
    p.append(f'<text x="{sg._fmt((ml + w - mr) / 2)}" y="{h - 8}" text-anchor="middle">'
             'total cycles for the run, n steps x estimated cycles/step (log)</text>')
    p.append(f'<text x="14" y="{sg._fmt((mt + h - mb) / 2)}" text-anchor="middle" '
             f'transform="rotate(-90 14 {sg._fmt((mt + h - mb) / 2)})">final-state error (log)</text>')
    # the epoch-1 budget, for scale
    bx = fx(65536)
    p.append(f'<line x1="{sg._fmt(bx)}" y1="{mt}" x2="{sg._fmt(bx)}" y2="{h - mb}" '
             'stroke="var(--text-3)" stroke-dasharray="4 3"/>')
    p.append(f'<text class="dlab" x="{sg._fmt(bx + 5)}" y="{mt + 14}">65,536-cycle budget</text>')
    for name in ("euler", "rk4", "sdirk2"):
        pts = series.get(name)
        if not pts:
            continue
        c = _SDIRK_COLORS.get(name, "var(--text-3)")
        path = " ".join(f"{'M' if i == 0 else 'L'} {sg._fmt(fx(x))} {sg._fmt(fy(y))}"
                        for i, (x, y) in enumerate(pts))
        p.append(f'<path d="{path}" fill="none" stroke="{c}" stroke-width="2"/>')
        m = methods[name]
        for (x, y) in pts:
            n = round(x / m["est_cycles_per_step"])
            p.append(f'<circle cx="{sg._fmt(fx(x))}" cy="{sg._fmt(fy(y))}" r="4" fill="{c}" '
                     f'class="cellstroke"><title>{sg._esc(name)} at n = {n} steps '
                     f'({int(x):,} cycles): error {_short(y)}</title></circle>')
        x0, y0 = pts[0]
        n0 = round(x0 / m["est_cycles_per_step"])
        dy = -10 if name != "euler" else 20
        p.append(f'<text class="dlab" x="{sg._fmt(fx(x0))}" y="{sg._fmt(fy(y0) + dy)}" '
                 f'text-anchor="middle">{sg._esc(name)}: stable from n = {n0}</text>')
    svg = (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
           'aria-label="SDIRK prototype stability curve on a ratio-1000 two-rate system: '
           'error against total cycles for euler, rk4 and sdirk2">' + "".join(p) + "</svg>")
    caption = ("Final-state error against total compute (n steps times estimated "
               "m0plus_fast cycles per step, both log) on a two-rate linear system with "
               "stiffness ratio 1000, float64 only. Each line starts at its method's "
               "cheapest <em>stable</em> run: everything to the left of a line's start "
               "diverged. sdirk2 is stable from 5 steps; rk4's line cannot begin until "
               "about 47,500 cycles, most of the epoch-1 budget (dashed vertical), and "
               "euler's until 10,000. Below the stability floor rk4's float64 accuracy "
               "is irrelevant because there is no stable run to have. Preliminary, "
               "off-archive prototype data.")
    legend = sg._legend([("var(--s1)", "sdirk2 (2-stage L-stable, 3 Newton iterations)"),
                         ("var(--s2)", "rk4"), ("var(--text-3)", "euler")])
    return _fig(svg, caption, legend,
                "data: rk-work/prototypes/sdirk_curve.json, problems.stiff_two_rate")


# ----------------------------------------------------------------------------- trade-offs

_DISC_LABEL = {"11e898cb": ("champion", "discovered champion"),
               "42863b93": ("elite3", "best order-3 elite"),
               "196b1d17": ("elite4", "best order-4 elite")}
_CLASSICAL_ROW_ORDER = ("euler", "midpoint", "heun2", "rk4", "rk38")
_LIB_ROW_ORDER = ("RK45", "Radau", "BDF", "LSODA")
_DASH = "&mdash;"


def _bench_load() -> dict:
    return _json_file(WS / "rk-work" / "benchmark" / "results.json",
                      "benchmark results.json")


def _tab_from_json(t: dict):
    A = [[Fraction(x) for x in row] for row in t["A"]]
    b = [Fraction(x) for x in t["b"]]
    c = [Fraction(x) for x in t["c"]]
    return tableau_mod.make_tableau(A, b, c)


def tradeoffs_matrix(vd: dict, bench: dict, kf: dict) -> str:
    methods = vd.get("methods") or []
    per = (vd.get("verdicts") or {}).get("per_problem") or {}
    results = vd.get("results") or []
    stiff_probs = {p["name"] for p in vd.get("problems", []) if p.get("stiff")}
    if not methods or not stiff_probs:
        print("WARN: validation methods/stiff subset missing; trade-offs matrix skipped")
        return ""
    # held-out error at budget, from the key-findings frontier (hash-matched)
    kf_rows = (kf.get("efficiency", {}).get("series", {})
               .get("frontier_cycles_vs_heldout") or [])
    heldout_by_name = {r.get("name"): r.get("heldout_error")
                       for r in kf_rows if r.get("kind") == "classical"}
    heldout_by_hash = {r.get("tableau_hash"): r.get("heldout_error")
                       for r in kf_rows if r.get("kind") == "discovered"}
    # outright validation wins per method, split practical / stiff
    wins: dict[str, list[int]] = {}
    for prob, v in per.items():
        w = str(v.get("winner"))
        wins.setdefault(w, [0, 0])[1 if v.get("stiff") else 0] += 1
    # measured Q15 seconds/step from the benchmark fixed-step table
    t_fixed: dict[str, list[float]] = {}
    for r in bench.get("fixed_step_results") or []:
        q = r.get("q15") or {}
        if q.get("status") == "ok" and isinstance(q.get("per_step_median_s"), (int, float)):
            t_fixed.setdefault(str(r.get("method")), []).append(q["per_step_median_s"])
    t_lib: dict[str, list[float]] = {}
    for r in bench.get("adaptive_results") or []:
        if r.get("status") == "ok" and isinstance(r.get("per_step_median_s"), (int, float)):
            t_lib.setdefault(str(r.get("integrator")), []).append(r["per_step_median_s"])

    def stiff_text(name: str) -> str:
        rows = [r for r in results if r.get("method") == name
                and str(r.get("problem")) in stiff_probs]
        fin = [str(r["problem"]) for r in rows
               if isinstance(r.get("q15_error"), (int, float))]
        over = [str(r["problem"]) for r in rows if r.get("note")]
        if not rows:
            return _DASH + '<sup>e</sup>'
        if not over:
            return f"finishes all {len(fin)}"
        if not fin:
            return f"overflows on all {len(over)}"
        return f"finishes {len(fin)} of {len(rows)}; overflows on {', '.join(over)}"

    def us(vals: list[float] | None) -> str:
        if not vals:
            return _DASH + '<sup>d</sup>'
        return f"{statistics.median(vals) * 1e6:,.0f}"

    header = ('<tr><th>method</th><th>kind</th><th class="num">order</th>'
              '<th class="num">stages</th>'
              '<th class="num">held-out error at budget<sup>a</sup></th>'
              '<th class="num">validation wins (practical / stiff)<sup>b</sup></th>'
              '<th class="num">cycles/step fast<sup>c</sup></th>'
              '<th class="num">cycles/step slow<sup>c</sup></th>'
              '<th class="num">CSD weight<sup>c</sup></th>'
              '<th class="num">measured &micro;s/step<sup>d</sup></th>'
              '<th>stiff validation subset<sup>e</sup></th>'
              "<th>notes</th></tr>")
    by_name = {str(m.get("name_or_hash")): m for m in methods}
    row_order: list[tuple[str, str, str, str]] = []   # (name_or_hash, label, kind, notes_key)
    for n in _CLASSICAL_ROW_ORDER:
        if n in by_name:
            row_order.append((n, n, "classical", n))
    for m in methods:
        n = str(m.get("name_or_hash"))
        if m.get("kind") == "discovered":
            key, desc = _DISC_LABEL.get(n[:8], (n[:8], "discovered"))
            row_order.append((n, f"{n[:8]} ({desc})", "discovered", key))
    rows_html = [header]
    for name, label, kind, notes_key in row_order:
        m = by_name[name]
        tb = _tab_from_json(m["tableau"])
        fast = costmodel.cycle_count(tb, costmodel.M0PLUS_FAST, 1)
        slow = costmodel.cycle_count(tb, costmodel.M0PLUS_SLOW, 1)
        csd = coeffrep.tableau_csd_total(tb)
        if kind == "classical":
            heldout = heldout_by_name.get(name)
        else:
            heldout = heldout_by_hash.get(name)
        w = wins.get(name, [0, 0])
        cell = label if kind == "classical" else f'<span class="hash">{label}</span>'
        rows_html.append(
            "<tr>"
            f"<td>{cell}</td><td>{kind}</td>"
            f'<td class="num">{m.get("order")}</td><td class="num">{m.get("stages")}</td>'
            f'<td class="num">{_short(heldout) if isinstance(heldout, (int, float)) else _DASH + "<sup>a</sup>"}</td>'
            f'<td class="num">{w[0]} / {w[1]}</td>'
            f'<td class="num">{fast}</td><td class="num">{slow}</td>'
            f'<td class="num">{csd}</td>'
            f'<td class="num">{us(t_fixed.get(name))}</td>'
            f"<td>{stiff_text(name)}</td>"
            f"<td>{T.TRADEOFFS_NOTES.get(notes_key, '')}</td>"
            "</tr>")
    for lib in _LIB_ROW_ORDER:
        if lib not in t_lib:
            continue
        rows_html.append(
            "<tr>"
            f"<td>{lib}</td><td>library (SciPy, float64, adaptive)</td>"
            f'<td class="num">{_DASH}</td><td class="num">{_DASH}</td>'
            f'<td class="num">{_DASH}<sup>a</sup></td>'
            f'<td class="num">{_DASH}<sup>b</sup></td>'
            f'<td class="num">{_DASH}<sup>c</sup></td><td class="num">{_DASH}<sup>c</sup></td>'
            f'<td class="num">{_DASH}<sup>c</sup></td>'
            f'<td class="num">{us(t_lib.get(lib))}</td>'
            f"<td>{_DASH}<sup>e</sup></td>"
            f"<td>{T.TRADEOFFS_NOTES.get(lib, '')}</td>"
            "</tr>")
    foot = """
<h3>Where each column comes from</h3>
<ol class="checks" style="font-size:13.5px">
<li><strong>a</strong> &mdash; held-out RMS error at the 65,536-cycle budget, m0plus_fast,
Q15 floor rounding: <code>tools/key_findings.json</code>,
series <code>frontier_cycles_vs_heldout</code>, matched by tableau hash. The library
integrators never ran this protocol (they are adaptive and float64), so those cells
hold no number.</li>
<li><strong>b</strong> &mdash; problems where this exact method has the lowest Q15 error of
all eight tested, from <code>rk-work/validation/results.json</code>,
<code>verdicts.per_problem.winner</code>; split as practical (5 non-stiff) / stiff (3).
Libraries are not part of the validation suite.</li>
<li><strong>c</strong> &mdash; analytic cycles per step (one state) and total CSD weight,
recomputed from each method's tableau in <code>rk-work/validation/results.json</code>
with the pinned <code>costmodel</code> and <code>coeffrep</code> modules. CSD weight is
the shift-add length of the coefficient multiplies, a code-size proxy. Adaptive
libraries have no fixed cycles per step.</li>
<li><strong>d</strong> &mdash; measured Python-level wall clock per step, the median across
the seven scored problems of per-problem medians (15 repeats, 3 warmups, gc paused),
from <code>rk-work/benchmark/results.json</code>. Q15 rows execute the pinned solver in
the Python interpreter; library rows run compiled internals, so times compare like
against like only within a regime. euler, midpoint, heun2 and rk38 were not part of the
benchmark run.</li>
<li><strong>e</strong> &mdash; behavior on the three stiff validation problems (stiffness
ratios 292 to 1030), from <code>rk-work/validation/results.json</code>; an overflow is a
<code>Q15OverflowError</code> raised by the pinned solver. The libraries were not run on
the stiff validation problems.</li>
</ol>
"""
    return ('<div class="scroll"><table>' + "".join(rows_html) + "</table></div>" + foot)


def tradeoffs_chips(vd: dict, bench: dict) -> str:
    bv = bench.get("verdicts") or {}
    per = (vd.get("verdicts") or {}).get("per_problem") or {}
    disc_wins = sum(1 for v in per.values() if v.get("winner_kind") == "discovered")
    items = []
    r = bv.get("median_ratio_q15_over_library_at_matched_tolerance")
    if isinstance(r, (int, float)):
        items.append((f"{r:,.0f}", "median best-Q15 / best-library error at matched tolerance"))
    compared = bv.get("fixed_step_cells_compared")
    lower = bv.get("fixed_step_cells_where_q15_error_lower")
    if isinstance(compared, int) and isinstance(lower, int):
        items.append((f"{compared - lower} of {compared}",
                      "matched-step cells where float64 rk4 is more accurate"))
    pr = (bench.get("correlation") or {}).get("pearson_r")
    if isinstance(pr, (int, float)):
        items.append((f"{pr:.3f}", "Pearson r, analytic cycles vs measured time/step"))
    if per:
        items.append((f"{disc_wins} of {len(per)}",
                      "validation problems won outright by a discovered method"))
    return _chips(items)


# ----------------------------------------------------------------------------- run charts

def _linear_line(points, w, h, xlabel, ylabel, aria) -> str:
    xlo, xhi = 0, max(x for x, _ in points) or 1
    ylo, yhi = 0, max(y for _, y in points) * 1.06 or 1
    ml, mr, mt, mb = 62, 14, 10, 38
    fx = lambda v: ml + (v - xlo) / (xhi - xlo) * (w - ml - mr)
    fy = lambda v: h - mb - (v - ylo) / (yhi - ylo) * (h - mt - mb)
    p = []
    for i in range(5):
        yv = ylo + (yhi - ylo) * i / 4
        p.append(f'<line class="gridline" x1="{ml}" y1="{sg._fmt(fy(yv))}" x2="{w - mr}" y2="{sg._fmt(fy(yv))}"/>')
        p.append(f'<text x="{ml - 6}" y="{sg._fmt(fy(yv) + 4)}" text-anchor="end">{int(yv):,}</text>')
    for i in range(6):
        xv = xlo + (xhi - xlo) * i / 5
        p.append(f'<text x="{sg._fmt(fx(xv))}" y="{h - mb + 16}" text-anchor="middle">{int(xv)}</text>')
    p.append(f'<line class="axis" x1="{ml}" y1="{h - mb}" x2="{w - mr}" y2="{h - mb}"/>')
    path = " ".join(f"{'M' if i == 0 else 'L'} {sg._fmt(fx(x))} {sg._fmt(fy(y))}"
                    for i, (x, y) in enumerate(points))
    p.append(f'<path d="{path}" fill="none" stroke="var(--s1)" stroke-width="2"/>')
    last = points[-1]
    p.append(f'<circle cx="{sg._fmt(fx(last[0]))}" cy="{sg._fmt(fy(last[1]))}" r="4" fill="var(--s1)" class="cellstroke">'
             f'<title>cycle {int(last[0])}: {int(last[1]):,} records</title></circle>')
    p.append(f'<text class="lbl" x="{sg._fmt(fx(last[0]) - 8)}" y="{sg._fmt(fy(last[1]) - 8)}" '
             f'text-anchor="end">{int(last[1]):,}</text>')
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
    svg = _linear_line(pts, 640, 310, "cycle", "records (cumulative)",
                       "Cumulative archive records against cycle number")
    return ('<figure><figcaption>Archive growth: only candidates that passed all nine '
            "verifier checks appear (rejections are counted separately, right). The jumps "
            "are the exhaustive phases; the flat stretch is the order-4 dry spell before "
            f"the projection fallback landed.</figcaption>{svg}</figure>")


def _count_bars(counts, w, aria, sw="var(--s1)") -> str:
    if not counts:
        return ""
    vmax = max(v for _k, v in counts)
    row_h, ml = 28, 190
    h = 12 + row_h * len(counts) + 8
    p = []
    for i, (k, v) in enumerate(counts):
        y = 8 + row_h * i
        bw = (v / vmax) * (w - ml - 76) if vmax else 0
        p.append(f'<text x="{ml - 6}" y="{sg._fmt(y + 14)}" text-anchor="end">{sg._esc(k)}</text>')
        p.append(f'<rect x="{ml}" y="{y}" width="{sg._fmt(max(bw, 2))}" height="19" rx="4" fill="{sw}" class="cellstroke">'
                 f'<title>{sg._esc(k)}: {v:,}</title></rect>')
        p.append(f'<text class="lbl" x="{sg._fmt(ml + max(bw, 2) + 6)}" y="{sg._fmt(y + 14)}">{v:,}</text>')
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{sg._esc(aria)}">'
            + "".join(p) + "</svg>")


def tier_chart(records) -> str:
    c = Counter(r.tier for r in records)
    rows = [(k, c.get(k, 0)) for k in ("heldout_verified", "search_only", "unreplicated")]
    return ('<figure><figcaption>Tier distribution over every archived record, assigned by '
            "code against each cell's incumbent: heldout_verified improved on both the "
            "search and held-out aggregates, search_only on search alone (the overfitting "
            "signature), unreplicated is everything else, including every record landing in "
            "an empty cell.</figcaption>"
            + _count_bars(rows, 560, "Records per confidence tier") + "</figure>")


def reject_chart(events) -> str:
    c = Counter(e.get("code") for e in events if e.get("kind") == "rejected")
    rows = sorted(((str(k), v) for k, v in c.items()), key=lambda kv: -kv[1])
    if not rows:
        return ""
    return ('<figure><figcaption>Verifier rejections by code, whole run; each candidate '
            "counts once, under the earliest of the nine ordered checks to fail. The cheap "
            "structural codes barely occur because enumeration and the exact-b projection "
            "emit only valid points.</figcaption>"
            + _count_bars(rows, 560, "Rejections per verifier code", sw="var(--s2)") + "</figure>")


# ----------------------------------------------------------------------------- phase-0 table

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

def _chips(items) -> str:
    return '<div class="chips">' + "".join(
        f'<div class="chip"><div class="v">{sg._esc(v)}</div><div class="k">{sg._esc(k)}</div></div>'
        for v, k in items) + "</div>"


def _finding(slug, num, title, intro, figures, interp) -> str:
    figs = "".join(f for f in figures if f)
    return (f'<section class="finding" id="{slug}">'
            f'<h2><span class="findnum">{num}</span>{sg._esc(title)}</h2>'
            f"{intro}{figs}{interp}</section>")


_BALANCED_TAGS = ("div", "section", "figure", "svg", "details", "table", "ul", "ol", "dl")


def _check_balance(name: str, html_text: str) -> bool:
    ok = True
    for tag in _BALANCED_TAGS:
        opens = len(re.findall(f"<{tag}[ >]", html_text))
        closes = html_text.count(f"</{tag}>")
        if opens != closes:
            print(f"WARN: {name}: <{tag}> open/close mismatch ({opens} vs {closes})")
            ok = False
    return ok


def build() -> None:
    records = archive.read_all()
    events = []
    ev_path = WS / "rk-work" / "events.jsonl"
    if ev_path.exists():
        for line in ev_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                ev = json.loads(line)
                if isinstance(ev, dict):
                    events.append(ev)
            except ValueError:
                pass
    kf = _kf_load()

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    n_cycles = (max((r.cycle_id for r in records), default=-1) + 1)
    n_rejected = sum(1 for e in events if e.get("kind") == "rejected")
    n_phases = len({e.get("phase") for e in events if isinstance(e.get("phase"), int)})

    # ---------------- index
    body = [T.HERO_LEAD]
    body.append(_chips([
        (f"{len(records):,}", "verified tableaus archived"),
        (f"{n_cycles:,}", "search cycles completed"),
        (f"{n_rejected:,}", "candidates rejected by the verifier"),
        (f"{TESTS_TOTAL:,}", "tests in the harness suite"),
        (f"{GATE_TESTS}", "tests at every container start"),
        (f"{n_phases}", "search phases exercised"),
    ]))
    body.append(T.INTRO)
    body.append("<h2>The findings, in one minute</h2>")
    body.append('<div class="teasers">' + "".join(
        f'<a class="tease" href="results.html#{slug}"><span class="tn">{i + 1}</span>'
        f'<span><span class="tt">{sg._esc(title)}.</span> '
        f'<span class="td">{sg._esc(desc)}</span></span></a>'
        for i, (slug, title, desc) in enumerate(T.TEASERS)) + "</div>")
    body.append("<h2>The anchor result</h2>")
    body.append('<div class="two">')
    body.append("<div>" + T.ANCHOR_TEXT + "</div>")
    body.append('<div class="panel">' + sg._anchor_bars().replace(
        'href="glossary.html#', 'href="findings/glossary.html#') + "</div>")
    body.append("</div>")
    body.append("<h2>Where to go</h2>")
    cards = [
        ("results.html", "Key findings", "Six findings, six charts, honest verdicts."),
        ("tradeoffs.html", "Trade-offs matrix",
         "Discovered vs classical vs library integrators, every cell traced to a data file."),
        ("tracks.html", "Research tracks",
         "The 70/15/15 rotation: epoch 1 closing, adaptive and implicit prototypes."),
        ("methodology.html", "Methodology",
         f"The start gate, the pinned hash, {TESTS_TOTAL:,} tests, the executed pre-flight."),
        ("architecture.html", "Architecture",
         "The container boundary, the cycle loop, the four-repository split."),
        ("design-decisions.html", "Design decisions",
         "Fourteen choices and what the build did to them."),
        ("findings/index.html", f"Findings snapshot ({SNAPSHOT_DATE})",
         "The machine-generated site, frozen at the snapshot date."),
        (LIVE_URL, "Live findings ↗",
         "The same machine-generated site, still updating with the run."),
    ]
    body.append('<div class="grid-cards">' + "".join(
        f'<a class="gcard" href="{href}"><div class="t">{sg._esc(t)}</div>'
        f'<div class="d">{sg._esc(d)}</div></a>' for href, t, d in cards) + "</div>")
    pages = {"index.html": _page(T.HERO_TITLE, "\n".join(body), "index.html",
                                 "An unattended search, a hash-pinned scorer, and what the "
                                 "numbers say so far.")}

    # ---------------- results (key findings)
    body = [T.HEADLINE_VERDICT]
    body.append(f'<p class="note">{sg._esc(T.RESULTS_SCOPE)}</p>')
    body.append('<ul class="toc">' + "".join(
        f'<li><a href="#{slug}">{i + 1} · {sg._esc(title)}</a></li>'
        for i, (slug, title, _d) in enumerate(T.TEASERS)) + "</ul>")
    body.append(_finding(
        "efficiency", 1, "The efficiency frontier: discovered methods lead in 13 of 14 cells",
        T.F_EFFICIENCY_INTRO, [frontier_chart(kf)], T.F_EFFICIENCY_INTERP))
    body.append(_finding(
        "floor-flip", 2, "Floor rounding reorders the classical field",
        T.F_FLIP_INTRO, [flip_slope_chart(kf), flip_problem_chart(kf)], T.F_FLIP_INTERP))
    body.append(_finding(
        "crossover", 3, "Where quantization overtakes truncation",
        T.F_CROSSOVER_INTRO, [crossover_chart(kf)], T.F_CROSSOVER_INTERP))
    body.append(_finding(
        "rc-thermal", 4, "The rc_thermal quantization floor",
        T.F_RC_INTRO, [rc_chart(kf)], T.F_RC_INTERP))
    p0_table = phase0_rows(records) if records else ""
    body.append(_finding(
        "phase0", 5, "Phase 0, closed: an exhaustive result",
        T.F_PHASE0_INTRO, [phase0_chart(kf)], T.F_PHASE0_INTERP + p0_table))
    vd = _validation_load()
    body.append(_finding(
        "validation", 6, "Practical validation: five problems nobody tuned for",
        T.F_VALIDATION_INTRO, [validation_chart(vd)], T.F_VALIDATION_INTERP))
    body.append("<h2>The run behind the numbers</h2>")
    body.append(T.RUN_CHARTS_INTRO)
    if records:
        last_ts = max(r.timestamp for r in records)
        body.append(f'<p class="note">Archive at this snapshot: {len(records):,} records; '
                    f"the latest was appended {sg._esc(timefmt.fmt_ct(last_ts))}.</p>")
    body.append(_panel(records_chart(records)))
    body.append('<div class="two">')
    body.append(_panel(tier_chart(records)))
    body.append(_panel(reject_chart(events)))
    body.append("</div>")
    pages["results.html"] = _page("key findings", "\n".join(body), "results.html",
                                  "What the search found, in six charts, at snapshot "
                                  f"{SNAPSHOT_DATE}.")

    # ---------------- research tracks
    ac = _json_file(WS / "rk-work" / "prototypes" / "adaptive_curve.json",
                    "adaptive_curve.json")
    sc = _json_file(WS / "rk-work" / "prototypes" / "sdirk_curve.json",
                    "sdirk_curve.json")
    body = [T.TRACKS_LEAD]
    body.append("<h2>Where the loop stands</h2>")
    body.append(orchestrator_panel())
    body.append(T.TRACKS_ORCH_NOTE)
    body.append("<h2>The rotation: 70/15/15</h2>")
    body.append(T.TRACKS_POLICY)
    body.append("<h2>Lead track (70%): epoch 1, explicit fixed-step</h2>")
    body.append(T.TRACK_A_MILESTONES.format(records=len(records), cycles=n_cycles))
    body.append("<h2>Side track B (15%): adaptive embedded pairs (epoch 2)</h2>")
    body.append(T.TRACK_B_INTRO)
    body.append(adaptive_curve_chart(ac))
    body.append(T.TRACK_B_INTERP)
    body.append("<h2>Side track C (15%): implicit SDIRK for stiff problems (epoch 3)</h2>")
    body.append(T.TRACK_C_INTRO)
    body.append(sdirk_chart(sc))
    body.append(T.TRACK_C_INTERP)
    body.append("<h2>Where it all lands</h2>")
    body.append('<p>Every track feeds the same destination: the '
                '<a href="tradeoffs.html">trade-offs matrix</a>, the paper\'s central '
                "table, already assembled from the epoch-1 data and rebuilt as each "
                "epoch adds its column of evidence.</p>")
    pages["tracks.html"] = _page("research tracks", "\n".join(body), "tracks.html",
                                 "The 70/15/15 rotation: one scored epoch, two side "
                                 "tracks, all showing measured artifacts.")

    # ---------------- trade-offs matrix
    bench = _bench_load()
    body = [T.TRADEOFFS_LEAD]
    body.append(tradeoffs_chips(vd, bench))
    body.append(T.TRADEOFFS_HOWTO)
    body.append("<h2>The matrix</h2>")
    body.append(tradeoffs_matrix(vd, bench, kf))
    body.append("<h2>Measurement caveats, verbatim</h2>")
    caveats = bench.get("caveats") or []
    if caveats:
        body.append("<ul>" + "".join(
            f"<li>{sg._esc(str(c))}</li>" for c in caveats) + "</ul>")
        body.append('<p class="note">Caveats copied from '
                    "<code>rk-work/benchmark/results.json</code>; the timing protocol "
                    f"(median of {int((bench.get('timing_protocol') or {}).get('n_repeats', 15))} "
                    "repeats after "
                    f"{int((bench.get('timing_protocol') or {}).get('warmup', 3))} warmups, "
                    "gc paused, BLAS threads capped) and the environment "
                    f"(Python {sg._esc(str((bench.get('environment') or {}).get('python', '?')))}, "
                    f"SciPy {sg._esc(str((bench.get('environment') or {}).get('scipy', '?')))}, "
                    f"NumPy {sg._esc(str((bench.get('environment') or {}).get('numpy', '?')))}) "
                    "are recorded in the same file.</p>")
    body.append("<h2>Reading it</h2>")
    body.append(T.TRADEOFFS_VERDICT)
    body.append('<p>The stiff column\'s failure pattern is measured in detail on the '
                '<a href="findings/validation.html">findings validation page</a> '
                "(stiff subset) and motivates "
                '<a href="tracks.html">research track C</a>.</p>')
    pages["tradeoffs.html"] = _page("trade-offs", "\n".join(body), "tradeoffs.html",
                                    "Discovered, classical and library methods in one "
                                    "table; every cell traced to a data file.")

    # ---------------- methodology (one skeleton, shared with the findings methodology)
    body = [T.METH_LEAD]
    body.append('<h2 id="setup">Experimental setup</h2>')
    body.append(T.METH_SETUP)
    body.append('<h2 id="measurement">Measurement</h2>')
    body.append(T.METH_MEASURE)
    body.append('<h2 id="protocol">Statistical protocol</h2>')
    body.append(T.METH_PROTOCOL)
    body.append('<h3 id="practical">Practical validation</h3>')
    body.append(T.METH_PRACTICAL)
    body.append('<h2 id="trust">Verification and trust</h2>')
    body.append(pipeline_diagram())
    body.append('<h3 id="gate">The gate at container start</h3>')
    body.append(T.METH_GATE)
    body.append("<h3>Ten files, one hash</h3>")
    body.append(T.METH_HASH)
    body.append("<h3>What the container cannot reach</h3>")
    body.append(T.METH_REACH)
    body.append('<h2 id="tests">Testing</h2>')
    body.append(T.METH_SUITE.format(tests=TESTS_TOTAL))
    body.append('<h3 id="preflight">The pre-flight, executed as a program</h3>')
    body.append(T.METH_PREFLIGHT)
    body.append('<h2 id="repro">Reproducibility</h2>')
    body.append(T.METH_REPRO)
    body.append('<h2 id="limits">Limitations</h2>')
    body.append(T.METH_LIMITS)
    pages["methodology.html"] = _page("methodology", "\n".join(body), "methodology.html",
                                      "The method: setup, measurement, protocol, trust, "
                                      "testing, and its limits.")

    # ---------------- architecture
    body = [T.ARCH_LEAD]
    body.append("<h2>The four repositories</h2>")
    body.append(repo_diagram())
    body.append(T.ARCH_REPOS)
    body.append("<h2>Trust boundaries</h2>")
    body.append(system_diagram())
    body.append(T.ARCH_BOUNDARIES)
    body.append("<h2>The cycle loop</h2>")
    body.append(cycle_diagram())
    body.append(T.ARCH_CYCLE)
    body.append("<h2>Verification, in order</h2>")
    body.append(T.ARCH_VERIFY)
    body.append('<h2 id="arithmetic">Arithmetic, exactly</h2>')
    body.append(T.ARCH_ARITH)
    body.append('<h2 id="costmodel">The cost model</h2>')
    body.append(T.ARCH_COSTMODEL)
    body.append('<h2 id="candidates">Where candidates come from</h2>')
    body.append(T.ARCH_CANDIDATES)
    body.append('<h2 id="archive">The archive</h2>')
    body.append(T.ARCH_ARCHIVE)
    body.append('<h2 id="outer">The outer loop: a research partner, not a sampler</h2>')
    body.append(T.ARCH_OUTER)
    body.append("<h2>The host layer</h2>")
    body.append(T.ARCH_HOST)
    pages["architecture.html"] = _page("architecture", "\n".join(body), "architecture.html",
                                       "The as-built system: repositories, boundaries, "
                                       "loop, arithmetic, search, host layer.")

    # ---------------- design decisions
    body = [f'<p class="note">{sg._esc(T.DECISIONS_LEAD)}</p>']
    body.append("<h3>Contents</h3>")
    body.append('<ul class="toc">' + "".join(
        f'<li><a href="#{slug}">{sg._esc(title)}</a></li>'
        for slug, title, _orig, _asbuilt in T.DECISIONS) + "</ul>")
    for slug, title, orig, asbuilt in T.DECISIONS:
        tag = ('<span class="tag tag-changed">revised in build</span>'
               if slug in REVISED_DECISIONS
               else '<span class="tag tag-kept">held up</span>')
        body.append(f'<div class="decision" id="{slug}">'
                    f'<h3><a href="#{slug}" style="color:inherit;text-decoration:none">'
                    f"{sg._esc(title)}</a>{tag}</h3>"
                    f'<div class="orig"><strong>Original:</strong> {orig}</div>'
                    f'<div class="asbuilt"><strong>As built:</strong> {asbuilt}</div>'
                    "</div>")
    body.append("<h2>What was deliberately cut</h2>")
    body.append(T.CUTS)
    body.append("<h2>Known prior art, and where the gap is</h2>")
    body.append(T.PRIOR_ART)
    pages["design-decisions.html"] = _page("design decisions", "\n".join(body),
                                           "design-decisions.html",
                                           "Every deliberate choice, annotated with what "
                                           "the build did to it.")

    all_ok = True
    for name, text in pages.items():
        if not _check_balance(name, text):
            all_ok = False
        (DOCS / name).write_text(text, encoding="utf-8")
        print("wrote", name, f"({len(text.encode('utf-8')) / 1024:.0f} KB)")
    if not all_ok:
        raise SystemExit("tag-balance check failed; see WARN lines above")

    # ---------------- findings snapshot (verbatim copy of the machine-generated site)
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
