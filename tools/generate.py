"""Build the rk-overview site into docs/.

Snapshot semantics: run by hand. Reads the live rk-work archive, tools/key_findings.json
(written by tools/key_findings.py), rk-work/validation/results.json,
rk-work/benchmark/results.json, tools/demo_data.json and the rk-harness test collection,
and writes five pages: index, architecture, design-decisions, results (key findings) and
demo. It deletes the retired pages and any old docs/findings copy so GitHub Pages stops
serving them. It reuses the findings site's style tokens and chart primitives so the two
sites read as one system. Timezone policy: stored data is UTC; anything rendered for
humans goes through rk_harness.timefmt (US Central), and SNAPSHOT_DATE is a Central date.

The prose lives in pages_text.py as str.format templates; every number in it is filled
here from the files above, and every pattern sentence is checked against the data
(_claim) so a stale sentence fails the build instead of shipping.

Before writing anything, every build checks the pages and fails loudly on unbalanced
tags, SVG text that leaves its viewBox (_audit_svg_text estimates each text node's
extent), and a bad link (_check_links: an internal href must name a page and an id on
it; a link into rk-findings must name a current page, and any fragment must be an id
that page is known to carry) or a dropped id (_check_incoming: every architecture id the
findings methodology page deep-links still exists here). After writing, it runs the two
headless node checks over
the pages that ship JavaScript (_check_scripts). Without node on the PATH it prints a
WARN, skips them and keeps the pages it wrote.

    cd rk-overview
    ..\\rk-harness\\.venv\\Scripts\\python.exe tools\\generate.py
"""
from __future__ import annotations

import json
import math
import re
import shutil
import statistics
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent            # rk-overview/
WS = ROOT.parent              # workspace
sys.path.insert(0, str(WS / "rk-harness"))
sys.path.insert(0, str(HERE))

import demo_page as _DEMO  # noqa: E402
import pages_text as T  # noqa: E402
from rk_harness import archive, methodology as meth, sitegen as sg  # noqa: E402
from rk_harness import coeffrep, costmodel  # noqa: E402
from rk_harness import tableau as tableau_mod  # noqa: E402
from rk_harness import timefmt  # noqa: E402

# The date the snapshot was taken, US Central. Derived in build() from the newest archive
# record, never hand-typed. The value below is only the fallback for an empty archive,
# which fails the build anyway.
SNAPSHOT_DATE = "unknown"
DOCS = ROOT / "docs"
LIVE_URL = T.LIVE_URL

# The five pages, in nav order, then the retired names the build deletes from docs/.
_NAV = (
    ("index.html", "overview"),
    ("architecture.html", "architecture"),
    ("design-decisions.html", "design decisions"),
    ("results.html", "key findings"),
    ("demo.html", "demo"),
)
_RETIRED = ("tradeoffs.html", "methodology.html", "tracks.html", "literature.html")

# The findings site's current pages. A link into rk-findings must name one of these.
_FINDINGS_PAGES = frozenset({"", "index.html", "explicit.html", "implicit.html",
                             "adaptive.html", "validation.html", "hypotheses.html",
                             "methodology.html"})
# The fragments a link into rk-findings may carry, per page: the section ids the findings
# generator publishes for linking, and on methodology.html every glossary term, read from
# sitegen._GLOSSARY so a renamed term fails this build rather than leaving a dead link. A
# page not listed here takes no fragment.
_FINDINGS_FRAGMENTS = {
    "validation.html": frozenset({"speed", "falsification"}),
    "hypotheses.html": frozenset({"interpretation", "literature"}),
    "methodology.html": frozenset({"costmodel", "ledger", "glossary"}
                                  | {anchor for anchor, _term, _paras in sg._GLOSSARY}),
}

# What each numbered test file covers. Counts are NOT here: they come from pytest
# collection at build time (_collect_suite), because a hand-kept table goes stale the
# first time anyone adds a test. A new tests/test_tN_*.py with no entry here fails the
# build rather than appearing blank. rk-harness hygiene C36 parses this literal, so keep
# its name and the closing brace in column 0.
_SUITE_DESC = {
    "T1": "fixed point, coefficient representation, cycle counting",
    "T2": "order conditions, evaluator, verifier",
    "T3": "archive, search, directive validation",
    "T4": "ledger, runner, site generator, epoch panel",
    "T5": "operational config, the watch view, status, checkout hygiene",
    "T6": "Central-time display formatting",
    "T7": "the findings methodology page",
    "T8": "the practical validation suite, stiff subset included",
    "T9": "the epoch saturation orchestrator",
    "T10": "the library benchmark harness",
    "T11": "the adaptive embedded-pair prototype",
    "T12": "the SDIRK implicit prototype",
    "T13": "the side-track executor and its ledger",
    "T14": "second-pass metrics over the archive: cycles to tolerance, the stability frontier",
    "T15": "the stiff-problem screen, admissions and rejections alike",
    "T16": "the lane scheduler, the lane cycle and the lane search",
    "T17": "the two-axis validation document across the three method classes",
    "T18": "the per-class findings pages: explicit, implicit, adaptive",
}

# Filled by _collect_suite() at the top of build(); read by the diagrams and the
# architecture page's testing section.
TESTS_TOTAL = 0
SUITE_TIERS: list[tuple[str, int, str]] = []
GATE_TESTS = 0


def _collect_suite() -> tuple[list[tuple[str, int, str]], int]:
    """Test counts straight from `pytest --collect-only` in rk-harness (about 2 seconds).

    Returns the tiers in numeric order and their total."""
    harness = WS / "rk-harness"
    python = harness / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = Path(sys.executable)
    proc = subprocess.run(
        [str(python), "-m", "pytest", "tests", "--collect-only", "-q"],
        cwd=str(harness), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300)
    rows: list[tuple[str, int]] = []
    for line in proc.stdout.splitlines():
        m = re.match(r"tests[/\\]test_(t\d+)_\w+\.py:\s*(\d+)\s*$", line.strip())
        if m:
            rows.append((m.group(1).upper(), int(m.group(2))))
    if not rows:
        tail = (proc.stdout[-800:] + proc.stderr[-800:]).strip()
        raise SystemExit("could not collect the test suite; run pytest in rk-harness "
                         f"first\n{tail}")
    # A tier can span several files (test_t5_config_watch.py and test_t5_status.py both
    # sit in T5), so counts are summed per tier rather than listed per file.
    totals: dict[str, int] = {}
    for tier, n in rows:
        totals[tier] = totals.get(tier, 0) + n
    undescribed = sorted(t for t in totals if t not in _SUITE_DESC)
    if undescribed:
        raise SystemExit(f"add {undescribed} to _SUITE_DESC in generate.py: the site says "
                         "what every test tier covers, so a new tier needs a description")
    tiers = [(t, totals[t], _SUITE_DESC[t]) for t in sorted(totals, key=lambda k: int(k[1:]))]
    return tiers, sum(n for _t, n, _d in tiers)


def _gate_count() -> int:
    """Size of the container's start gate: the node ids in tests/golden_gate.txt."""
    path = WS / "rk-harness" / "tests" / "golden_gate.txt"
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    n = sum(1 for ln in lines if ln and not ln.startswith("#"))
    if not n:
        raise SystemExit(f"{path} lists no tests")
    return n


# Decisions whose plan changed on contact with the build (tagged on the page).
REVISED_DECISIONS = {"credentials", "numbers-not-claims", "q15-overflow"}

# Page-specific components only. All shared chrome (font stack, heading scale, nav,
# footer, tables, figures, cards, details/summary, palette tokens) comes from
# sitegen._STYLE unchanged, so the two sites read as siblings.
_EXTRA_STYLE = """
.herolead{font-size:17.5px;line-height:1.6;max-width:74ch}
nav.tabs a.ext{margin-left:auto;color:var(--s1);font-weight:600}
nav.tabs a.ext:hover{color:var(--text-1)}
/* On a phone the nav wraps rather than scrolling sideways: a scrolling row put the
   active tab off-screen on the two right-most pages. Each tab becomes its own rounded
   box, so a second row reads as part of the nav instead of a strip cut loose from the
   rule under the header. */
@media (max-width:560px){nav.tabs{flex-wrap:wrap;gap:4px}
  nav.tabs a{padding:7px 10px;border-radius:8px;border:1px solid transparent}
  nav.tabs a.on{border-color:var(--line);box-shadow:none}
  nav.tabs a.ext{margin-left:0}}
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
.two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;
  align-items:start}
@media (max-width:900px){.two{grid-template-columns:minmax(0,1fr)}}
.two>.panel{overflow-x:auto}
/* On a phone every chart and diagram keeps its drawn size and scrolls inside its panel,
   rather than shrinking until its labels cannot be read. The gradients are a scroll cue:
   the inner pair fades the panel background over the cut edge and the outer pair is a
   shadow that only shows while there is more to scroll to, so a diagram that runs past
   the screen does not read as one box in an empty panel. */
@media (max-width:700px){figure .scroll svg,.two>.panel svg{max-width:none}
  figure .scroll,.two>.panel{background:
    linear-gradient(90deg,var(--surface-1) 30%,transparent),
    linear-gradient(270deg,var(--surface-1) 30%,transparent) 100% 0,
    radial-gradient(farthest-side at 0 50%,rgba(0,0,0,.18),transparent),
    radial-gradient(farthest-side at 100% 50%,rgba(0,0,0,.18),transparent) 100% 0;
    background-repeat:no-repeat;
    background-size:28px 100%,28px 100%,14px 100%,14px 100%;
    background-attachment:local,local,scroll,scroll}}
.wrap>ul li{max-width:82ch}
p.verdict{font-size:16px;line-height:1.65;max-width:82ch}
section.finding{margin:44px 0;scroll-margin-top:16px}
section.finding h2{font-size:20px;margin-bottom:8px}
.findnum{display:inline-grid;place-items:center;width:30px;height:30px;border-radius:9px;
  background:var(--s1);color:#fff;font-size:16px;font-weight:700;margin-right:12px;
  vertical-align:-7px}
figure .src{display:block;margin-top:6px;font-size:12px;color:var(--text-3)}
pre.grammar{font:12.5px ui-monospace,Consolas,monospace;background:var(--surface-1);
  border:1px solid var(--line);border-radius:8px;padding:10px 14px;overflow-x:auto}
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
svg .dashedbox{stroke-dasharray:6 4}
svg .arrow{stroke:var(--text-3);fill:none;marker-end:url(#ah);stroke-width:1.5}
svg .arrowdash{stroke-dasharray:6 4}
svg .enclosure{fill:none;stroke:var(--text-3);stroke-dasharray:4 4;opacity:.7}
svg a text{fill:var(--s1)}
ol.checks li{margin:6px 0;max-width:82ch}
ol.checks.foot{font-size:13.5px;list-style:none;padding-left:0}
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

/* Landing page: a bigger opening, then a four-step spine. The rest of the site keeps
   the compact scale; only the front door is allowed to be loud. */
body.home header.site h1{font-size:34px;line-height:1.15;max-width:22ch}
@media (max-width:640px){body.home header.site h1{font-size:26px}}
body.home .herolead{font-size:18.5px;line-height:1.55;max-width:66ch;margin:14px 0 0}
.spine{display:grid;gap:0;margin:34px 0 8px;border-top:1px solid var(--line)}
.spine section{padding:20px 0 18px;border-bottom:1px solid var(--line);
  display:grid;grid-template-columns:120px minmax(0,1fr);gap:4px 28px;align-items:start}
@media (max-width:760px){.spine section{grid-template-columns:1fr;gap:6px}}
.spine .k{grid-row:1 / span 3;font-size:11px;font-weight:700;letter-spacing:.1em;
  text-transform:uppercase;color:var(--s1);padding-top:5px}
@media (max-width:760px){.spine .k{grid-row:auto}}
.spine h2{margin:0;font-size:19px;line-height:1.3;letter-spacing:-.012em;max-width:34ch}
.spine p{margin:8px 0 0;font-size:14.5px;color:var(--text-2);max-width:70ch}
.spine .more{font-size:13px;font-weight:600;text-decoration:none;margin-top:10px;
  display:inline-block}
.spine .more:hover{text-decoration:underline}
"""


def _nav(active: str) -> str:
    """One row: the five pages, then the live findings site, styled apart as a link."""
    tabs = "".join(
        f'<a href="{href}"{" class=" + chr(34) + "on" + chr(34) if href == active else ""}>'
        f"{sg._esc(label)}</a>" for href, label in _NAV)
    return (f'<nav class="tabs">{tabs}'
            f'<a class="ext" href="{LIVE_URL}">live findings &#8599;</a></nav>')


def _page(title: str, body: str, active: str, subtitle: str = "",
          head_extra: str = "", body_end: str = "") -> str:
    sub = f'<p class="sub">{sg._esc(subtitle)}</p>' if subtitle else ""
    footer = T.FOOTER.format(date=SNAPSHOT_DATE)
    # Only the landing page opens loud; every other page keeps the compact scale.
    cls = ' class="home"' if active == "index.html" else ""
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{sg._esc(title)}</title>\n"
        f"<style>{sg._STYLE}{_EXTRA_STYLE}</style>\n{head_extra}</head>\n<body{cls}>\n"
        '<header class="site"><div class="wrap">\n'
        f"<h1>{sg._esc(title)}</h1>\n{sub}\n"
        f"{_nav(active)}\n"
        "</div></header>\n"
        '<div class="wrap">\n'
        f"{body}\n"
        f"<footer>{sg._esc(footer)}</footer>\n"
        "</div>\n"
        f"{body_end}"
        "</body>\n</html>\n"
    )


def _t(template: str, **ctx) -> str:
    """Fill a pages_text template. {live} is always the findings site root."""
    return template.format(live=LIVE_URL, **ctx)


def _claim(ok: bool, what: str) -> None:
    """A pattern sentence in pages_text must still match the data, or the build stops."""
    if not ok:
        raise SystemExit(f"pages_text no longer matches the data: {what}. Rewrite the "
                         "sentence rather than publishing a stale claim.")


def _fig(svg: str, caption_html: str, legend: str = "", source: str = "") -> str:
    """A key-findings figure, caption-first like the findings site's charts."""
    if not svg:
        return ""
    src = f'<span class="src">{sg._esc(source)}</span>' if source else ""
    return (f'<figure class="panel"><figcaption>{caption_html}{src}</figcaption>'
            + legend + f'<div class="scroll">{svg}</div></figure>')


def _fold(summary: str, inner: str) -> str:
    """A secondary figure behind a <details>, or nothing when the figure is absent."""
    if not inner:
        return ""
    return (f'<details class="fold"><summary>{sg._esc(summary)}</summary><div>{inner}'
            "</div></details>")


def _short(v: float) -> str:
    return f"{v:.3g}"


def _fr(x) -> str:
    """An exact fraction for prose: '13/16', '0', '-4'; minus signs typeset."""
    return str(Fraction(str(x))).replace("-", "&minus;")


def _pct(x: float, nd: int = 1) -> str:
    s = f"{100 * x:.{nd}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


# ----------------------------------------------------------------------------- diagrams
# Boxes are sized from their content: ~8.6 px/char for 15px semibold titles and
# ~7.35 px/char for 14px body lines, plus padding, so labels never overflow.

_TCH, _LCH = 8.6, 7.35


def _natw(title: str, lines: list[str], pad: int = 26) -> int:
    widths = [len(title) * _TCH] + [len(ln) * _LCH for ln in lines]
    return int(max(widths) + pad)


def _nath(lines: list[str]) -> int:
    return 40 if not lines else 44 + 19 * len(lines)


def _marker_sprite() -> str:
    """The arrowhead the architecture diagrams share, defined once at the top of the page.

    One zero-size svg holds the definition, so the page has a single id="ah" however many
    diagrams it draws. display:none would stop Chrome drawing the markers."""
    return ('<svg width="0" height="0" aria-hidden="true" style="position:absolute">'
            '<defs><marker id="ah" markerWidth="9" markerHeight="9" refX="8" refY="4.5" '
            'orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="var(--text-3)"/></marker>'
            '</defs></svg>')


def _box(x, y, w, title, lines, cls="box", extra_cls="") -> str:
    h = _nath(lines)
    c = f"{cls} {extra_cls}".strip()
    out = [f'<rect class="{c}" x="{x}" y="{y}" width="{w}" height="{h}" rx="9"/>',
           f'<text class="bt" x="{x + 13}" y="{y + 23}">{sg._esc(title)}</text>']
    for i, ln in enumerate(lines):
        out.append(f'<text class="bs" x="{x + 13}" y="{y + 45 + 19 * i}">{sg._esc(ln)}</text>')
    return "".join(out)


def _arrow(x1, y1, x2, y2, label="", lx=None, ly=None, dashed=False,
           anchor="middle") -> str:
    cls = "arrow arrowdash" if dashed else "arrow"
    out = [f'<path class="{cls}" d="M {x1} {y1} L {x2} {y2}"/>']
    if label:
        out.append(f'<text class="alab" x="{lx if lx is not None else (x1 + x2) / 2}" '
                   f'y="{ly if ly is not None else (y1 + y2) / 2 - 6}" '
                   f'text-anchor="{anchor}">{sg._esc(label)}</text>')
    return "".join(out)


def _badge(x, y, text, bg, fg) -> str:
    w = len(text) * 7 + 14
    return (f'<rect x="{x}" y="{y}" width="{w}" height="19" rx="9" fill="{bg}"/>'
            f'<text x="{x + w / 2}" y="{y + 13.5}" text-anchor="middle" '
            f'style="font-size:11px;font-weight:700;fill:{fg}">{sg._esc(text)}</text>')


def repo_diagram() -> str:
    """The four public repositories, with the live/snapshot cue for the two sites."""
    b1t, b1l = "rk-harness", ["the scorer: verifier, evaluator,",
                              f"cost models, {TESTS_TOTAL:,} tests",
                              "read-only in the container"]
    b2t, b2l = "rk-work", ["run data: append-only archive,",
                           "hypothesis ledger, results",
                           "the one writable mount"]
    b3t, b3l = "rk-findings", ["machine-generated numbers site,",
                               "rebuilt by the run every cycle"]
    b4t, b4l = "rk-overview  (this site)", ["hand-written explainer pages,",
                                            "built from the archive by hand"]
    lab_a, lab_b = "verifies + scores", "rebuilt every cycle"
    w1, w2 = _natw(b1t, b1l), _natw(b2t, b2l)
    w3 = max(_natw(b3t, b3l), int(len(b3t) * _TCH) + 13 + 58 + 18)
    # room for the corner badge beside the title
    w4 = max(_natw(b4t, b4l), int(len(b4t) * _TCH) + 13 + 84 + 18)
    gap_a = int(len(lab_a) * 6.4) + 26   # arrow gaps sized to their labels
    gap_b = int(len(lab_b) * 6.4) + 26
    x1, y1 = 20, 46
    x2 = x1 + w1 + gap_a
    x3 = x2 + w2 + gap_b
    h1, h2, h3, h4 = _nath(b1l), _nath(b2l), _nath(b3l), _nath(b4l)
    y4 = y1 + max(h1, h2) + 96
    live_lab = "jgoetzmann.github.io/rk-findings ↗ (live)"
    W = int(max(x3 + w3, x3 + len(live_lab) * 6.9, x2 + w4)) + 20
    H = y4 + h4 + 46
    p = []
    # container enclosure around the two mounted repos
    p.append(f'<rect class="enclosure" x="{x1 - 10}" y="{y1 - 26}" '
             f'width="{x2 + w2 - x1 + 20}" height="{max(h1, h2) + 40}" rx="12"/>')
    p.append(f'<text class="alab" x="{x1 - 2}" y="{y1 - 32}">mounted into the run container</text>')
    p.append(_box(x1, y1, w1, b1t, b1l, cls="boxhl"))
    p.append(_box(x2, y1, w2, b2t, b2l))
    p.append(_box(x3, y1, w3, b3t, b3l))
    p.append(_badge(x3 + w3 - 58, y1 + 10, "LIVE", "var(--good-bg)", "var(--good-fg)"))
    p.append(_box(x2, y4, w4, b4t, b4l, extra_cls="dashedbox"))
    p.append(_badge(x2 + w4 - 84, y4 + 10, "SNAPSHOT", "var(--mut-bg)", "var(--mut-fg)"))
    p.append(_arrow(x1 + w1, y1 + h1 / 2, x2, y1 + h2 / 2, lab_a))
    p.append(_arrow(x2 + w2, y1 + h2 / 2, x3, y1 + h3 / 2, lab_b))
    ax = x2 + 40
    p.append(f'<path class="arrow arrowdash" d="M {ax} {y1 + h2} L {ax} {y4 - 2}"/>')
    p.append(f'<text class="alab" x="{ax + 10}" y="{y1 + max(h1, h2) + 38}">'
             f"read by a hand-run build, {SNAPSHOT_DATE}</text>")
    p.append(f'<a href="{LIVE_URL}"><text class="alab" x="{x3}" y="{y1 + h3 + 18}" '
             f'style="fill:var(--s1)">{live_lab}</text></a>')
    p.append(f'<text class="alab" x="{x2}" y="{y4 + h4 + 18}">'
             "jgoetzmann.github.io/rk-overview (you are here)</text>")
    svg = (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
           'aria-label="The four repositories: rk-harness and rk-work mounted into the '
           'container, rk-findings rebuilt every cycle and published live, rk-overview a '
           'snapshot built from rk-work by hand">' + "".join(p) + "</svg>")
    return ('<figure class="panel"><figcaption>One writer and one trust level per '
            "repository. Boxes are git repositories and the dashed enclosure is the "
            "container boundary. The findings site moves with the run; this site is a "
            "snapshot.</figcaption>"
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

    p = []
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
    # Diagonal labels sit beside their arrows, never on them. The push label rides above
    # the start of its falling line. The two rising lines into the right column run nearly
    # parallel, so the LLM label goes above its line near the arrowhead and the commit
    # label below its line near the start, each where the other line is far away.
    p.append(_arrow(x1 + c1w, y + hosth + 60, x2, wy + 20, lab_push,
                    lx=x1 + c1w + 8, ly=y + hosth + 60 - 8, anchor="start"))
    p.append(_arrow(x2 + c2w, ry + ih_run / 2, x3, y_cx + cxh / 2, lab_llm,
                    lx=x3 - 10, ly=y_cx + cxh / 2 - 10, anchor="end"))
    p.append(_arrow(x2 + c2w, wy + 20, x3, y_fin + finh / 2, lab_commit,
                    lx=x2 + c2w + 8, ly=wy + 20 + 18, anchor="start"))
    p.append(_arrow(x3 + c3w / 2, y_fin + finh, x3 + c3w / 2, y_pg))
    H = max(y + cont_h, y_pg + _nath(pgl)) + 16
    svg = (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
           'aria-label="System diagram: host, container with read-only harness, and services">'
           + "".join(p) + "</svg>")
    return ('<figure class="panel"><figcaption>The system as built, left to right: the '
            "Windows host, the docker container, and the services the run talks to. The "
            "verifier sits inside the read-only mount, and no arrow carries the GitHub "
            "credential into the container.</figcaption>"
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
    p = []
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
           'aria-label="Explicit cycle: replay, encourager, candidates, verify, evaluate, '
           'tier, append, ledger, site, commit">' + "".join(p) + "</svg>")
    return ('<figure class="panel"><figcaption>One explicit cycle, along the top row and '
            "then the bottom.</figcaption>"
            f'<div class="scroll">{svg}</div></figure>')


def pipeline_diagram() -> str:
    """The container start gate, in execution order, with the exit-1 branch."""
    chain = [
        ("container start", []),
        ("1 · write heartbeat", ["the first line of the entrypoint"]),
        ("2 · read-only probe", ["a write to /harness must fail"]),
        ("3 · verifier hash check", ["sha256 over ten files vs the pinned value"]),
        ("4 · golden + canary tests", [f"{GATE_TESTS} cases with pytest"]),
        ("runner starts", ["science on a proven environment only"]),
    ]
    failt = "exit 1"
    faill = ["the runner never starts;", "the watchdog restarts, the gate re-runs"]
    cw = max(_natw(t, ls) for t, ls in chain)
    fw = _natw(failt, faill)
    gap_y = 30
    x, y = 16, 16
    fx = x + cw + 96
    p = []
    ys = []
    for t, ls in chain:
        h = _nath(ls)
        hl = t == "runner starts"
        p.append(_box(x, y, cw, t, ls, cls="boxhl" if hl else "box"))
        ys.append((y, h))
        y += h + gap_y
    for (by, bh), (ny, _nh) in zip(ys, ys[1:]):
        p.append(_arrow(x + cw / 2, by + bh, x + cw / 2, ny - 2))
    # exit-1 branch: a rail collecting the three steps that can fail. The heartbeat write
    # ends in `|| true` in entrypoint.sh, so it has no failure path.
    checks = ys[2:5]
    fail_top = checks[0][0]
    fail_bot = checks[-1][0] + checks[-1][1]
    fh = _nath(faill)
    fy = (fail_top + fail_bot) / 2 - fh / 2
    railx = x + cw + 46
    p.append(f'<rect class="boxbad" x="{fx}" y="{fy}" width="{fw}" height="{fh}" rx="9"/>')
    p.append(f'<text x="{fx + 13}" y="{fy + 23}" style="font-weight:650;font-size:15px;'
             f'fill:var(--bad-fg)">{failt}</text>')
    for i, ln in enumerate(faill):
        p.append(f'<text x="{fx + 13}" y="{fy + 45 + 19 * i}" style="font-size:14px;'
                 f'fill:var(--bad-fg)">{sg._esc(ln)}</text>')
    for by, bh in checks:
        p.append(f'<path d="M {x + cw} {by + bh / 2} L {railx} {by + bh / 2}" '
                 'stroke="var(--bad-fg)" fill="none" opacity=".55"/>')
    # The rail runs from the top stub to the bottom one, so every check reaches it.
    top_mid = checks[0][0] + checks[0][1] / 2
    p.append(f'<path d="M {railx} {top_mid} L {railx} {checks[-1][0] + checks[-1][1] / 2}" '
             'stroke="var(--bad-fg)" fill="none" opacity=".55"/>')
    p.append(f'<path d="M {railx} {fy + fh / 2} L {fx - 2} {fy + fh / 2}" '
             'stroke="var(--bad-fg)" fill="none" marker-end="url(#ah)"/>')
    p.append(f'<text class="alab" x="{railx}" y="{top_mid - 10}" '
             'text-anchor="middle" style="fill:var(--bad-fg)">any failure</text>')
    W = fx + fw + 16
    H = y - gap_y + 16
    svg = (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
           'aria-label="Start gate: heartbeat, read-only probe, hash check, golden and '
           'canary tests, then the runner; a failed check exits">' + "".join(p) + "</svg>")
    return ('<figure class="panel"><figcaption>The start gate, top to bottom, on every '
            "container start. The runner starts only after the read-only probe, the hash "
            "check and the golden and canary tests pass against the harness as mounted. "
            "The tests run at start rather than at image build, so every restart repeats "
            "them.</figcaption>"
            f'<div class="scroll">{svg}</div></figure>')


# ----------------------------------------------------------------------------- key-findings charts

def _kf_load() -> dict:
    path = HERE / "key_findings.json"
    if not path.exists():
        raise SystemExit("tools/key_findings.json is missing; run tools/key_findings.py first")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        raise SystemExit("tools/key_findings.json is unparsable; rerun tools/key_findings.py")


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
    budget = kf["efficiency"]["numbers"]["budget_cycles"]
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
                 f'best classical method ({_short(best_classical)})</text>')
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
    caption = (f"Per-step cost against held-out error at the shared {budget:,}-cycle budget, "
               "both on log scales, so down and left is better. Every blue dot under the "
               "dashed line has lower error than every classical method.")
    legend = sg._legend([("var(--s1)", "discovered (best per grid cell)"),
                         ("var(--s2)", "classical methods")])
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
    for rank in range(1, len(methods) + 1):
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
    caption = ("Each line is one method, ranked by search-set RMS error under each rounding "
               "mode, with the value beside each end. Blue is euler, orange rk4. "
               "Round-to-nearest was rerun outside the archive as the counterfactual.")
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
    H = 16 + sum(head_h + row_h * len(_METHOD_ORDER) + group_pad for _ in problems) + 52
    p = []
    for tv in (1e-4, 1e-3, 1e-2, 1e-1, 1):
        px = fx(tv)
        p.append(f'<line class="gridline" x1="{sg._fmt(px)}" y1="10" x2="{sg._fmt(px)}" y2="{H - 48}"/>')
        p.append(f'<text x="{sg._fmt(px)}" y="{H - 30}" text-anchor="middle">{sg._pow_label(tv)}</text>')
    p.append(f'<text x="{sg._fmt((ml + w - mr) / 2)}" y="{H - 10}" text-anchor="middle">'
             'final-state error at the shared budget (log)</text>')
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
    caption = ("Final-state error per problem and method, log scale, left is better. The "
               "bar between the two dots is what the rounding mode alone changes.")
    legend = sg._legend([("var(--s1)", "floor (ASRS, as measured)"),
                         ("var(--s2)", "round-to-nearest (counterfactual)")])
    return _fig(svg, caption, legend, "data: key_findings.json, series per_problem_floor_vs_round")


def crossover_chart(kf: dict) -> str:
    sweeps = _series(kf, "crossover", "sweeps")
    if not sweeps:
        return ""
    nums = kf.get("crossover", {}).get("numbers", {})
    methods = nums.get("methods", {})
    w, h, ml, mr, mt, mb = 880, 480, 70, 36, 44, 52
    xlo, ylo, yhi = 0.008, 1e-11, 1e2

    # The findings site leaves out float64 points whose error is above 1
    # (sitegen._sweep_chart): no Q15 state can hold a value that large, and plotting those
    # runs stretches the axis over twenty decades until the Q15 curves are a few pixels
    # tall. Applying the same rule here keeps the two sites on one point set of the same
    # experiment, and the caption names the step sizes left out. The x domain follows the
    # points that survive, so a run the rule keeps cannot fall off the right edge.
    def shown(r, key: str) -> bool:
        v = r.get(key)
        return (isinstance(v, (int, float)) and ylo <= v <= yhi
                and not (key == "float_error" and v > 1.0))

    dropped = {m: sorted(r["h"] for r in sweeps.get(m, [])
                         if r.get("h") and isinstance(r.get("float_error"), (int, float))
                         and r["float_error"] > 1.0)
               for m in ("rk4", "heun2")}
    drawn_h = [r["h"] for m in ("rk4", "heun2") for r in sweeps.get(m, [])
               if r.get("h") and (shown(r, "q15_error") or shown(r, "float_error"))]
    xhi = max(1.6, 1.1 * max(drawn_h)) if drawn_h else 1.6
    fx = lambda v: _logpos(v, xlo, xhi, ml, w - mr)
    fy = lambda v: h - mb - _logpos(v, ylo, yhi, 0, h - mt - mb)
    p = []
    for tv in [t for t in (0.01, 0.05, 0.1, 0.5, 1, 2) if t < xhi]:
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
    for mname, cross_label_y in (("rk4", mt + 14), ("heun2", mt + 30)):
        cross = methods.get(mname, {}).get("crossover_h")
        if isinstance(cross, (int, float)) and xlo < cross < xhi:
            px = fx(cross)
            p.append(f'<line x1="{sg._fmt(px)}" y1="{mt}" x2="{sg._fmt(px)}" y2="{h - mb}" '
                     'stroke="var(--text-3)" stroke-dasharray="4 3"/>')
            p.append(f'<text class="dlab" x="{sg._fmt(px + 5)}" y="{cross_label_y}">'
                     f'{sg._esc(mname)} crossover h = {_short(cross)}</text>')
    for mname in ("rk4", "heun2"):
        rows = [r for r in sweeps.get(mname, []) if r.get("h")]
        c = colors[mname]
        for key, dash in (("q15_error", ""), ("float_error", ' stroke-dasharray="6 4"')):
            pts = [(r["h"], r[key]) for r in rows if shown(r, key)]
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
                # where the two methods sit decades apart
                h0, e0 = pts[0]
                p.append(f'<text class="dlab" x="{sg._fmt(fx(h0) + 10)}" '
                         f'y="{sg._fmt(fy(e0) - 8)}">{sg._esc(mname)}</text>')
    problem = nums.get("problem", "the test problem")
    svg = (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
           f'aria-label="Step-size sweep on {sg._esc(problem)}: Q15 and float64 error for rk4 and '
           'heun2, log-log, with crossover markers">' + "".join(p) + "</svg>")
    def _hs(vals) -> str:
        s = [_short(v) for v in vals]
        return s[0] if len(s) == 1 else ", ".join(s[:-1]) + " and " + s[-1]

    off = "; ".join(f"{mname} at h = {_hs(dropped[mname])}"
                    for mname in ("rk4", "heun2") if dropped[mname])
    caption = (f"Final-state error on {sg._esc(problem)} against step size, both axes log. "
               "Solid lines are Q15, dashed lines float64 over the same steps. Left of each "
               "vertical marker the Q15 line turns up while float64 keeps falling. Q15 runs "
               "that overflowed at the largest steps are left out."
               + (f" So are float64 errors above 1, which no Q15 state can hold: {off}."
                  if off else ""))
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
    order = [m for m in _RC_ORDER if m in by] + sorted(m for m in by if m not in _RC_ORDER)
    groups = [(m, by[m]) for m in order] + ([("best discovered", None)] if best else [])
    w, h, ml, mr, mt, mb = 880, 400, 64, 20, 24, 66
    ymax = 0.22
    fy = lambda v: h - mb - (v / ymax) * (h - mt - mb)
    p = []
    for tv in (0, 0.05, 0.10, 0.15, 0.20):
        p.append(f'<line class="gridline" x1="{ml}" y1="{sg._fmt(fy(tv))}" x2="{w - mr}" y2="{sg._fmt(fy(tv))}"/>')
        p.append(f'<text x="{ml - 8}" y="{sg._fmt(fy(tv) + 4)}" text-anchor="end">{_tickfmt(tv)}</text>')
    p.append(f'<line class="axis" x1="{ml}" y1="{h - mb}" x2="{w - mr}" y2="{h - mb}"/>')
    p.append(f'<text x="14" y="{sg._fmt((mt + h - mb) / 2)}" text-anchor="middle" '
             f'transform="rotate(-90 14 {sg._fmt((mt + h - mb) / 2)})">final-state error</text>')
    gw = (w - ml - mr) / len(groups)
    bar_w, gap = 26, 4
    n_round = 0
    for gi, (name, r) in enumerate(groups):
        cx = ml + gw * gi + gw / 2
        if r is not None:
            fe, re_ = r["floor_error"], r.get("round_error")
            bx = cx - (bar_w + gap / 2 if re_ is not None else bar_w / 2)
            p.append(sg._round_top_bar(bx, fy(fe), bar_w, (h - mb) - fy(fe), "var(--s1)",
                                       f"{name} floor: error {_short(fe)}; {r['steps']:,} steps; "
                                       f"final Q15 state {tuple(r['final_state_q15'])}"))
            if re_ is not None:
                n_round += 1
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
    lo, hi = nums.get("floor_error_min"), nums.get("floor_error_max")
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
        # Halfway between the tallest bar (or the reference line) and the top of the
        # plot, so the note crosses no bar.
        ann = (max(hi, ref if isinstance(ref, (int, float)) else hi) + ymax) / 2
        p.append(f'<text class="dlab" x="{ml + 6}" y="{sg._fmt(fy(ann) + 4)}">'
                 f'floor: {_short(lo)} to {_short(hi)} for all {len(rows)}</text>')
    svg = (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
           'aria-label="rc_thermal error per method under floor and round-to-nearest, '
           'with the reference norm marked">' + "".join(p) + "</svg>")
    caption = ("Final-state error on rc_thermal. Every floor bar (blue) reaches the dashed "
               "line, the size of the true solution, because the state collapsed to near "
               f"zero. Orange: round-to-nearest, measured for {n_round} methods. Green: the "
               "best discovered method on rc_thermal (not the finding 1 champion), under "
               "the same floor arithmetic.")
    legend = sg._legend([("var(--s1)", "floor (ASRS, as measured)"),
                         ("var(--s2)", "round-to-nearest (counterfactual)"),
                         ("var(--s3)", "best discovered, still under floor")])
    return _fig(svg, caption, legend, "data: key_findings.json, series per_method")


def phase0_chart(kf: dict) -> str:
    rows = _series(kf, "phase0_exhaustive", "all_members")
    if not rows:
        return ""
    rows = sorted(rows, key=lambda r: Fraction(r["a21"]))
    n = len(rows)
    n_named = sum(1 for r in rows if r.get("name"))
    w, h, ml, mr, mt, mb = 880, 380, 64, 20, 24, 58
    ylo, yhi = 0.05, 0.145
    fy = lambda v: h - mb - (v - ylo) / (yhi - ylo) * (h - mt - mb)
    slot = (w - ml - mr) / n
    p = []
    for tv in (0.06, 0.08, 0.10, 0.12, 0.14):
        p.append(f'<line class="gridline" x1="{ml}" y1="{sg._fmt(fy(tv))}" x2="{w - mr}" y2="{sg._fmt(fy(tv))}"/>')
        p.append(f'<text x="{ml - 8}" y="{sg._fmt(fy(tv) + 4)}" text-anchor="end">{_tickfmt(tv)}</text>')
    p.append(f'<line class="axis" x1="{ml}" y1="{h - mb}" x2="{w - mr}" y2="{h - mb}"/>')
    p.append(f'<text x="{sg._fmt((ml + w - mr) / 2)}" y="{h - 8}" text-anchor="middle">'
             f'a21, ordered by value (one dot per exactly representable tableau, {n} in all)</text>')
    p.append(f'<text x="14" y="{sg._fmt((mt + h - mb) / 2)}" text-anchor="middle" '
             f'transform="rotate(-90 14 {sg._fmt((mt + h - mb) / 2)})">held-out error</text>')
    for i, r in enumerate(rows):
        cx = ml + slot * i + slot / 2
        cy = fy(r["heldout_error"])
        named = r.get("name")
        fill = "var(--s1)" if r["rank"] == 1 else ("var(--s2)" if named else "var(--text-3)")
        title = (f"a21 = {r['a21']}, b = ({r['b'][0]}, {r['b'][1]}): held-out error "
                 f"{_short(r['heldout_error'])}, {r['cycles']} cycles/step, rank {r['rank']} of {n}"
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
           'aria-label="Phase 0 exhaustive: held-out error for every two-stage order-2 '
           'tableau in the lattice, ordered by a21">' + "".join(p) + "</svg>")
    caption = (f"All {n} members of the phase-0 space by a21, held-out error on a linear "
               f"scale (lower is better). Blue is the optimum, orange the {n_named} textbook "
               "methods, gray the rest.")
    return _fig(svg, caption, "", "data: key_findings.json, series all_members")


def _validation_load() -> dict:
    return _json_file(WS / "rk-work" / "validation" / "results.json",
                      "validation results.json")


def validation_chart(vd: dict) -> str:
    """Dumbbell per practical problem: best classical vs best discovered Q15 error.
    Scoped to the non-stiff problems; the stiff subset is overflow, not accuracy, and
    lives on the findings validation page."""
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
    budget = vd.get("budget_cycles")
    vals = [v for _n, d in rows for v in (d["best_classical_q15_error"],
                                          d["best_discovered_q15_error"])]
    w, ml, mr = 880, 150, 30
    xlo = 10 ** math.floor(math.log10(min(vals)))
    xhi = 10 ** math.ceil(math.log10(max(vals)))
    fx = lambda v: _logpos(v, xlo, xhi, ml, w - mr)
    row_h = 56
    H = 16 + row_h * len(rows) + 54
    p = []
    tv = xlo
    while tv <= xhi * 1.0001:
        px = fx(tv)
        p.append(f'<line class="gridline" x1="{sg._fmt(px)}" y1="10" x2="{sg._fmt(px)}" y2="{H - 50}"/>')
        p.append(f'<text x="{sg._fmt(px)}" y="{H - 32}" text-anchor="middle">{sg._pow_label(tv)}</text>')
        tv *= 10
    p.append(f'<text x="{sg._fmt((ml + w - mr) / 2)}" y="{H - 10}" text-anchor="middle">'
             f'final-state Q15 error at the {budget:,}-cycle budget (log)</text>')
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
    tail = (f"; on {', '.join(losses)} the classical method keeps the win"
            if losses else "")
    caption = (f"Final-state Q15 error per practical problem at the {budget:,}-cycle budget, "
               "log scale, left is better. Orange is the best classical method (named), blue "
               f"the best discovered one, which is ahead on {len(wins)} of {len(rows)}{tail}.")
    legend = sg._legend([("var(--s1)", "best discovered"),
                         ("var(--s2)", "best classical method")])
    return _fig(svg, caption, legend, "data: rk-work/validation/results.json, verdicts.per_problem")


def speedup_chart(bench: dict) -> str:
    """Predicted vs measured per-step speedup of the champion over rk4, per problem."""
    sp = bench.get("speedup") or {}
    rows = [r for r in (sp.get("rows") or []) if r.get("status") == "ok"]
    if not rows:
        print("WARN: speedup rows missing; speedup chart skipped")
        return ""
    tp = bench.get("timing_protocol") or {}
    w, ml, mr = 780, 130, 96
    top, row_h, bot = 40, 40, 46
    H = top + row_h * len(rows) + bot
    xlo, xhi = 0.95, 1.78
    fx = lambda v: ml + (v - xlo) / (xhi - xlo) * (w - ml - mr)
    p = []
    for tv in (1.0, 1.2, 1.4, 1.6):
        p.append(f'<line class="gridline" x1="{sg._fmt(fx(tv))}" y1="{top - 6}" '
                 f'x2="{sg._fmt(fx(tv))}" y2="{H - bot + 6}"/>')
        p.append(f'<text x="{sg._fmt(fx(tv))}" y="{H - bot + 22}" text-anchor="middle">{tv:g}&times;</text>')
    p.append(f'<line x1="{sg._fmt(fx(1.0))}" y1="{top - 6}" x2="{sg._fmt(fx(1.0))}" y2="{H - bot + 6}" '
             'stroke="var(--text-3)" stroke-dasharray="4 3"/>')
    p.append(f'<text class="alab" x="{sg._fmt(fx(1.0))}" y="{top - 12}" text-anchor="middle">parity</text>')
    for i, r in enumerate(rows):
        cy = top + row_h * i + row_h / 2
        meas = r["measured_ratio_rk4_over_champion"]
        pred = r["predicted_ratio_rk4_over_champion"]
        xm, xp = fx(meas), fx(pred)
        p.append(f'<text x="{ml - 10}" y="{sg._fmt(cy + 4)}" text-anchor="end">{sg._esc(r["problem"])}</text>')
        p.append(f'<line x1="{sg._fmt(min(xm, xp))}" y1="{sg._fmt(cy)}" x2="{sg._fmt(max(xm, xp))}" '
                 f'y2="{sg._fmt(cy)}" stroke="var(--line)" stroke-width="2"/>')
        title = (f"{r['problem']}: measured {meas:.3f}x ({r['champion_us_per_step']:.1f} vs "
                 f"{r['rk4_us_per_step']:.1f} us/step over {r['champion_n_steps']:,} vs "
                 f"{r['rk4_n_steps']:,} steps); cycle model predicts {pred:.2f}x "
                 f"({r['champion_cycles_per_step']} vs {r['rk4_cycles_per_step']} cycles); "
                 f"error ratio champion/rk4 {r['error_ratio_champion_over_rk4']:.3f}")
        p.append(f'<circle cx="{sg._fmt(xp)}" cy="{sg._fmt(cy)}" r="5" fill="var(--surface-1)" '
                 f'stroke="var(--s2)" stroke-width="2.5"><title>{sg._esc(title)}</title></circle>')
        p.append(f'<circle cx="{sg._fmt(xm)}" cy="{sg._fmt(cy)}" r="5.5" fill="var(--s1)" '
                 f'class="cellstroke"><title>{sg._esc(title)}</title></circle>')
        p.append(f'<text class="dlab" x="{sg._fmt(max(xm, xp) + 12)}" y="{sg._fmt(cy + 4)}">'
                 f'{meas:.2f}&times;</text>')
        if i == 0:
            # Name the two markers once, on the header line with "parity", clear of every
            # row. The left marker's name ends at it and the right one's starts at it, so
            # the names cannot overlap whichever way round the markers fall.
            (xa, la), (xb, lb) = sorted(((xm, "measured"), (xp, "cycle model")))
            p.append(f'<text class="alab" x="{sg._fmt(xa + 4)}" y="{top - 12}" '
                     f'text-anchor="end">{la}</text>')
            p.append(f'<text class="alab" x="{sg._fmt(xb - 4)}" y="{top - 12}">{lb}</text>')
    p.append(f'<text x="{sg._fmt((ml + w - mr) / 2)}" y="{H - 8}" text-anchor="middle">'
             'per-step speedup, rk4 time over champion time (above 1 means the champion is faster)</text>')
    svg = (f'<svg viewBox="0 0 {w} {H}" width="{w}" height="{H}" role="img" '
           'aria-label="Measured and cycle-model-predicted per-step speedup of the champion '
           'over rk4 on each scored problem">' + "".join(p) + "</svg>")
    gm = sp.get("geomean_measured_speedup_rk4_over_champion")
    gp = sp.get("geomean_predicted_speedup_rk4_over_champion")
    caption = ("Per-step speedup of the champion over rk4 on each scored problem. Blue is "
               f"measured wall clock (median of {tp.get('n_repeats')} repeats after "
               f"{tp.get('warmup')} warmups), open orange the cycle model's prediction of "
               f"{gp:.2f}&times;; the measured geometric mean is {gm:.2f}&times;.")
    return _fig(svg, caption, "", "data: rk-work/benchmark/results.json, speedup.rows")


def grid_coverage_chart(records, orders) -> str:
    """The MAP-Elites lattice: which of the searchable cells hold an elite.

    The lattice is not orders x stages x buckets: an order can only use stage counts that
    can reach it, so the size is summed per order from encourager.stage_domain, the same
    source the findings site uses.
    """
    grids = archive._grids_from(records, orders)
    classical_hashes = {tableau_mod.content_hash(t): n
                        for n, t in tableau_mod.classical().items()}
    cell, pitch = 18, 20
    x0, top = 16, 40
    rowlab_w, group_gap = 30, 34
    p = []
    x = x0
    n_occ = n_disc = n_clas = n_out = 0
    n_cells = sum(len(sg.encourager.stage_domain(o)) * 8 for o in (1, 2, 3, 4))
    max_rows = 0
    for order in (1, 2, 3, 4):
        grid = grids.get(order, {})
        domain = set(sg.encourager.stage_domain(order))
        stage_rows = sorted(set(range(2, 7)) | {s for (s, _b) in grid})
        max_rows = max(max_rows, len(stage_rows))
        gx = x + rowlab_w
        p.append(f'<text class="dlab" x="{gx}" y="{top - 14}">order {order}</text>')
        for i, s in enumerate(stage_rows):
            cy = top + pitch * i
            p.append(f'<text x="{gx - 6}" y="{sg._fmt(cy + cell / 2 + 3.5)}" text-anchor="end" '
                     f'style="font-size:11px">s{s}</text>')
            for b in range(8):
                cx = gx + pitch * b
                rec = grid.get((s, b))
                if rec is None:
                    p.append(f'<rect x="{cx}" y="{cy}" width="{cell}" height="{cell}" rx="3" '
                             f'fill="var(--surface-1)" stroke="var(--grid)">'
                             f'<title>order {order}, {s} stages, bucket {b}: empty</title></rect>')
                    continue
                if s not in domain:
                    # Occupied but outside what the search can reach: a seeded baseline.
                    # Counted beside the fraction, never into it.
                    n_out += 1
                    p.append(f'<rect x="{cx}" y="{cy}" width="{cell}" height="{cell}" rx="3" '
                             f'fill="var(--s2)" class="cellstroke"><title>order {order}, {s} stages, '
                             f'bucket {b}: seeded baseline, outside the searched stage range</title></rect>')
                    continue
                n_occ += 1
                cname = classical_hashes.get(rec.tableau_hash)
                if cname:
                    n_clas += 1
                    fill, who = "var(--s2)", f"classical baseline {cname}"
                else:
                    n_disc += 1
                    fill, who = "var(--s1)", f"discovered {rec.tableau_hash[:12]}"
                p.append(f'<rect x="{cx}" y="{cy}" width="{cell}" height="{cell}" rx="3" '
                         f'fill="{fill}" class="cellstroke"><title>order {order}, {s} stages, '
                         f'bucket {b}: {who}, held-out error '
                         f'{_short(rec.score.heldout_error)}</title></rect>')
        p.append(f'<text x="{gx}" y="{top + pitch * len(stage_rows) + 14}" '
                 f'style="font-size:11px">b0</text>')
        p.append(f'<text x="{gx + pitch * 7 + cell}" y="{top + pitch * len(stage_rows) + 14}" '
                 f'text-anchor="end" style="font-size:11px">b7</text>')
        x = gx + pitch * 7 + cell + group_gap
    W = x - group_gap + 16
    H = top + pitch * max_rows + 44
    p.append(f'<text x="{x0 + rowlab_w}" y="{H - 8}">columns are cycle-cost buckets '
             'b0..b7 (log2 bands of cycles/step, m0plus_fast); rows are stage counts</text>')
    svg = (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
           'aria-label="Archive grid coverage: occupied MAP-Elites cells per order, '
           'stage count and cycle bucket">' + "".join(p) + "</svg>")
    outside = ""
    if n_out:
        outside = (f" {n_out} more {'cell' if n_out == 1 else 'cells'} (euler, at one "
                   f"stage) {'sits' if n_out == 1 else 'sit'} outside the searched range.")
    seeded = "a seeded classical method" if n_clas == 1 else "seeded classical methods"
    caption = (f"Which of the {n_cells} searchable MAP-Elites cells hold an elite: "
               f"{n_occ} are occupied, {n_disc} by discovered methods and {n_clas} by "
               f"{seeded}.{outside} The upper cost buckets are empty by "
               "construction, since no step at 2 to 6 stages costs that much under the fast "
               "multiplier.")
    legend = sg._legend([("var(--s1)", "held by a discovered method"),
                         ("var(--s2)", "held by a classical method")])
    return _fig(svg, caption, legend, "data: rk-work archive, MAP-Elites cells at generation time")


# ----------------------------------------------------------------------------- method matrix

_DISC_LABEL = {"11e898cb": ("champion", "discovered champion"),
               "42863b93": ("elite3", "best order-3 elite"),
               "196b1d17": ("elite4", "best order-4 elite")}
_CLASSICAL_ROW_ORDER = ("euler", "midpoint", "heun2", "rk4", "rk38")
_LIB_ROW_ORDER = ("RK45", "Radau", "BDF", "LSODA")
_NA = "n/a"


def _json_file(path: Path, label: str) -> dict:
    if not path.exists():
        print(f"WARN: {label} missing; section skipped")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        print(f"WARN: {label} unparsable; section skipped")
        return {}


def _bench_load() -> dict:
    return _json_file(WS / "rk-work" / "benchmark" / "results.json",
                      "benchmark results.json")


def _tab_from_json(t: dict):
    A = [[Fraction(x) for x in row] for row in t["A"]]
    b = [Fraction(x) for x in t["b"]]
    c = [Fraction(x) for x in t["c"]]
    return tableau_mod.make_tableau(A, b, c)


def method_matrix(vd: dict, bench: dict, kf: dict, foot: str) -> str:
    methods = vd.get("methods") or []
    per = (vd.get("verdicts") or {}).get("per_problem") or {}
    results = vd.get("results") or []
    stiff_probs = {p["name"] for p in vd.get("problems", []) if p.get("stiff")}
    if not methods or not stiff_probs:
        print("WARN: validation methods/stiff subset missing; method matrix skipped")
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
    for _prob, v in per.items():
        wins.setdefault(str(v.get("winner")), [0, 0])[1 if v.get("stiff") else 0] += 1
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
            return _NA + "<sup>e</sup>"
        if not over:
            return f"finishes all {len(fin)}"
        if not fin:
            return f"overflows on all {len(over)}"
        return f"finishes {len(fin)} of {len(rows)}; overflows on {', '.join(over)}"

    def us(vals: list[float] | None) -> str:
        if not vals:
            return _NA + "<sup>d</sup>"
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
        heldout = heldout_by_name.get(name) if kind == "classical" else heldout_by_hash.get(name)
        w = wins.get(name, [0, 0])
        cell = label if kind == "classical" else f'<span class="hash">{label}</span>'
        rows_html.append(
            "<tr>"
            f"<td>{cell}</td><td>{kind}</td>"
            f'<td class="num">{m.get("order")}</td><td class="num">{m.get("stages")}</td>'
            f'<td class="num">{_short(heldout) if isinstance(heldout, (int, float)) else _NA + "<sup>a</sup>"}</td>'
            f'<td class="num">{w[0]} / {w[1]}</td>'
            f'<td class="num">{fast}</td><td class="num">{slow}</td>'
            f'<td class="num">{csd}</td>'
            f'<td class="num">{us(t_fixed.get(name))}</td>'
            f"<td>{stiff_text(name)}</td>"
            f"<td>{T.MATRIX_NOTES.get(notes_key, '')}</td>"
            "</tr>")
    for lib in _LIB_ROW_ORDER:
        if lib not in t_lib:
            continue
        rows_html.append(
            "<tr>"
            f"<td>{lib}</td><td>library (SciPy, float64, adaptive)</td>"
            f'<td class="num">{_NA}</td><td class="num">{_NA}</td>'
            f'<td class="num">{_NA}<sup>a</sup></td>'
            f'<td class="num">{_NA}<sup>b</sup></td>'
            f'<td class="num">{_NA}<sup>c</sup></td><td class="num">{_NA}<sup>c</sup></td>'
            f'<td class="num">{_NA}<sup>c</sup></td>'
            f'<td class="num">{us(t_lib.get(lib))}</td>'
            f"<td>{_NA}<sup>e</sup></td>"
            f"<td>{T.MATRIX_NOTES.get(lib, '')}</td>"
            "</tr>")
    return ('<div class="scroll"><table>' + "".join(rows_html) + "</table></div>" + foot)


def heldout_chart(kf: dict, vd: dict) -> str:
    """The matrix's held-out-error column drawn as a dot chart, one row per method."""
    eff = kf.get("efficiency", {})
    budget = (eff.get("numbers") or {}).get("budget_cycles")
    anchors = (eff.get("numbers") or {}).get("classical_anchors") or []
    kf_rows = (eff.get("series") or {}).get("frontier_cycles_vs_heldout") or []
    heldout_by_hash = {r.get("tableau_hash"): r.get("heldout_error")
                       for r in kf_rows if r.get("kind") == "discovered"}
    entries = [(a["name"], float(a["heldout_error"]), "classical") for a in anchors
               if isinstance(a.get("heldout_error"), (int, float))]
    for m in vd.get("methods") or []:
        if m.get("kind") != "discovered":
            continue
        hsh = str(m.get("name_or_hash"))
        he = heldout_by_hash.get(hsh)
        if isinstance(he, (int, float)):
            _key, desc = _DISC_LABEL.get(hsh[:8], (hsh[:8], "discovered"))
            entries.append((f"{hsh[:8]} ({desc})", float(he), "discovered"))
    if len(entries) < 4:
        print("WARN: too few methods with held-out error; held-out chart skipped")
        return ""
    entries.sort(key=lambda e: e[1])
    w, ml, mr = 780, 224, 88
    row_h, top, bot = 27, 14, 46
    H = top + row_h * len(entries) + bot
    xlo = 10 ** math.floor(math.log10(min(e[1] for e in entries)))
    xhi = 10 ** math.ceil(math.log10(max(e[1] for e in entries)))
    fx = lambda v: _logpos(v, xlo, xhi, ml, w - mr)
    p = []
    tv = xlo
    while tv <= xhi * 1.0001:
        p.append(f'<line class="gridline" x1="{sg._fmt(fx(tv))}" y1="{top - 4}" '
                 f'x2="{sg._fmt(fx(tv))}" y2="{H - bot + 4}"/>')
        p.append(f'<text x="{sg._fmt(fx(tv))}" y="{H - bot + 20}" text-anchor="middle">{sg._pow_label(tv)}</text>')
        tv *= 10
    for i, (name, err, kind) in enumerate(entries):
        cy = top + row_h * i + row_h / 2
        c = "var(--s1)" if kind == "discovered" else "var(--s2)"
        p.append(f'<text x="{ml - 10}" y="{sg._fmt(cy + 4)}" text-anchor="end">{sg._esc(name)}</text>')
        p.append(f'<line x1="{ml}" y1="{sg._fmt(cy)}" x2="{sg._fmt(fx(err))}" y2="{sg._fmt(cy)}" '
                 'stroke="var(--grid)" stroke-width="1.5"/>')
        p.append(f'<circle cx="{sg._fmt(fx(err))}" cy="{sg._fmt(cy)}" r="5.5" fill="{c}" '
                 f'class="cellstroke"><title>{sg._esc(name)}: held-out error {_short(err)} '
                 f'at the {budget:,}-cycle budget</title></circle>')
        p.append(f'<text class="dlab" x="{sg._fmt(fx(err) + 10)}" y="{sg._fmt(cy + 4)}">{_short(err)}</text>')
    p.append(f'<text x="{sg._fmt((ml + w - mr) / 2)}" y="{H - 8}" text-anchor="middle">'
             f'held-out RMS error at the {budget:,}-cycle budget (log; left is better)</text>')
    svg = (f'<svg viewBox="0 0 {w} {H}" width="{w}" height="{H}" role="img" '
           'aria-label="Held-out error at the shared budget for every scored method, '
           'discovered and classical, log scale">' + "".join(p) + "</svg>")
    caption = (f"Held-out RMS error at the {budget:,}-cycle budget for every scored method, "
               "best at the top, log scale. The libraries never ran this protocol, so they "
               "have no dot.")
    legend = sg._legend([("var(--s1)", "discovered"), ("var(--s2)", "classical")])
    return _fig(svg, caption, legend,
                "data: tools/key_findings.json, frontier series and classical anchors")


_COST_ROLES = {"m0plus_fast": "M0+ with a single-cycle multiplier; primary",
               "m0plus_slow": "M0+ with an iterative multiplier; primary",
               "avr_approx": "8-bit AVR approximation; advisory only"}


def _cost_table() -> str:
    """The three cost models, read from the pinned costmodel module."""
    ops = ("mul", "add", "shift", "load", "store")
    head = "".join(f'<th class="num">{o}</th>' for o in ops)
    rows = "".join(
        f"<tr><td>{sg._esc(name)}</td>"
        + "".join(f'<td class="num">{m.cycles[o]}</td>' for o in ops)
        + f"<td>{sg._esc(_COST_ROLES.get(name, ''))}</td></tr>"
        for name, m in costmodel.COST_MODELS.items())
    return (f'<div class="scroll"><table><thead><tr><th>model</th>{head}<th>role</th></tr>'
            f"</thead><tbody>{rows}</tbody></table></div>")


def _anchor_costs() -> dict:
    """rk4 and rk38 cycles per step, one state, under the two M0+ models."""
    cl = tableau_mod.classical()
    out = {}
    for name in ("rk4", "rk38"):
        out[f"{name}_fast"] = costmodel.cycle_count(cl[name], costmodel.M0PLUS_FAST, 1)
        out[f"{name}_slow"] = costmodel.cycle_count(cl[name], costmodel.M0PLUS_SLOW, 1)
    _claim(out["rk4_fast"] < out["rk38_fast"] and out["rk38_slow"] < out["rk4_slow"],
           "the anchor result says rk4 is cheaper fast and rk38 cheaper slow")
    return out


# ----------------------------------------------------------------------------- page data

def _check_scripts() -> None:
    """Run the headless checks over the two pages that ship JavaScript.

    Both load the published page, drive every control, and compare what the page computes
    against data derived independently: demo.html against the pinned Python evaluator,
    index.html against the ranking its own data implies. Skipped with a warning when node
    is missing."""
    node = shutil.which("node")
    if node is None:
        print("WARN: node not found; skipped the demo and landing-widget checks "
              "(run `node tools/check_demo.js` and `node tools/check_hero.js`)")
        return
    for script, page in (("check_demo.js", "demo.html"), ("check_hero.js", "index.html")):
        proc = subprocess.run([node, str(HERE / script), str(DOCS / page)],
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        for line in (proc.stdout + proc.stderr).splitlines():
            if line.strip():
                print(line)
        if proc.returncode != 0:
            raise SystemExit(f"{page} failed its self-check")


def _hero_data(demo: dict) -> dict:
    """The landing widget's data: one error per (problem, mode, method).

    Reduced from demo_data.json so the index ships about 3 KB instead of the demo page's
    120 KB, and so both pages rank the same numbers."""
    methods = [{"key": m["key"], "label": m["label"], "origin": m["origin"]}
               for m in demo["methods"]]
    order = {m["key"]: i for i, m in enumerate(methods)}
    err: dict[str, dict[str, list]] = {}
    for row in demo["expected"]:
        slot = err.setdefault(row["p"], {})
        vals = slot.setdefault(row["mode"], [None] * len(methods))
        if row.get("status") == "ok":
            vals[order[row["m"]]] = row.get("error")
    return {"methods": methods,
            "problems": [p["name"] for p in demo["problems"]],
            "default_problem": "damped_osc",
            "err": err}


def _demo_load() -> dict:
    """tools/demo_data.json, written by tools/demo_data.py. Inlined into demo.html."""
    path = HERE / "demo_data.json"
    if not path.exists():
        raise SystemExit("tools/demo_data.json is missing; run tools/demo_data.py first")
    return json.loads(path.read_text(encoding="utf-8"))


def _join(items: list[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _eff_ctx(kf: dict, records, orders) -> dict:
    """Counts that appear in prose on more than one page.

    They used to be typed into pages_text.py by hand and drifted a cycle behind
    key_findings.json, so the index said 14 of 15 cells while the results page said 13 of
    14. Every one of them is now derived here and formatted into the text."""
    n = kf["efficiency"]["numbers"]
    grids = archive._grids_from(records, orders)
    seeded = {tableau_mod.content_hash(t): name for name, t in tableau_mod.classical().items()}
    cells = sorted(((order, s, b), rec) for order, g in grids.items()
                   for (s, b), rec in g.items())
    hv = sum(1 for _k, rec in cells
             if rec.tier == "heldout_verified" and rec.tableau_hash not in seeded)
    class_cells = [seeded[rec.tableau_hash] for _k, rec in cells if rec.tableau_hash in seeded]
    won, disc = (n["cells_where_discovered_beats_all_cheaper_or_equal_anchors"],
                 n["cells_held_by_discovered"])
    ctx = {
        "cells_total": n["grid_cells_total"],
        "cells_disc": disc,
        "cells_class": n["cells_held_by_classical"],
        "class_cells": _join(class_cells),
        "cells_won": won,
        "cells_hv": hv,
        "median_ratio": f"{n['median_error_ratio_discovered_over_anchor']:.2f}",
        "best_ratio": f"{n['best_error_ratio']:.2f}",
        "best_x": f"{1 / n['best_error_ratio']:.2f}",
        "archive_n": f"{n['archive_records']:,}",
        "cycles_n": f"{n['last_cycle_id'] + 1:,}",
        "budget": f"{n['budget_cycles']:,}",
    }
    ctx["won_sentence"] = (T.F_EFFICIENCY_WON_ALL if won == disc
                           else T.F_EFFICIENCY_WON_SOME).format(**ctx)
    ctx["eff_title"] = (T.F_EFFICIENCY_TITLE_ALL if won == disc
                        else T.F_EFFICIENCY_TITLE_SOME).format(**ctx)
    return ctx


def _mat(rows) -> str:
    return "[" + ", ".join("[" + ", ".join(_fr(x) for x in r) + "]" for r in rows) + "]"


def _vec(v) -> str:
    return "(" + ", ".join(_fr(x) for x in v) + ")"


def _results_ctx(kf: dict, vd: dict, bench: dict, eff: dict) -> dict:
    """Every number the key-findings, architecture and decisions prose needs.

    Each value is read from key_findings.json, validation/results.json or
    benchmark/results.json; each pattern the prose states in words is checked here
    (_claim), so a refreshed analysis that breaks a sentence fails the build."""
    ctx = dict(eff)
    ctx.update(_anchor_costs())

    # finding 1: the best discovered method against the best classical one
    n = kf["efficiency"]["numbers"]
    bd = n["best_discovered"]
    anchor = min(n["classical_anchors"], key=lambda a: a["heldout_error"])
    tab = bd["tableau"]
    coeffs = [Fraction(x) for row in tab["A"] for x in row] + [
        Fraction(x) for x in tab["b"] + tab["c"]]
    _claim(all(f.denominator & (f.denominator - 1) == 0 for f in coeffs),
           "finding 1 says every coefficient of the best discovered method is dyadic")
    ctx.update(
        bd_stages=bd["stages"], bd_order=bd["order"], bd_cycles=bd["cycles"],
        bd_err=_short(bd["heldout_error"]), anchor_err=_short(anchor["heldout_error"]),
        anchor_name=anchor["name"], bd_A=_mat(tab["A"]), bd_b=_vec(tab["b"]),
        bd_c=_vec(tab["c"]), bd_measured=f"{bd['measured_order']:.2f}",
        bd_per_problem=", ".join(f"{k} {_short(v)}"
                                 for k, v in bd["per_problem_heldout"].items()),
        bd_tier=bd["tier"])

    # finding 2: floor against round-to-nearest
    agg = kf["floor_bias_flip"]["numbers"]["aggregate"]
    fl, rd = agg["floor"]["search_rms"], agg["round_to_nearest"]["search_rms"]
    n_flip = len(fl["rank"])
    _claim(fl["rank"]["euler"] == 1 and fl["rank"]["rk4"] == n_flip,
           "finding 2 says floor puts euler first and rk4 last on the search set")
    _claim(rd["rank"]["rk4"] < rd["rank"]["euler"],
           "finding 2 says round-to-nearest puts rk4 ahead of euler")
    series = kf["floor_bias_flip"]["series"]["per_problem_floor_vs_round"]
    problems = sorted({r["problem"] for r in series})
    changed = 0
    for pr in problems:
        rows = [r for r in series if r["problem"] == pr]
        fmin = min(r["floor_error"] for r in rows)
        rmin = min(r["round_error"] for r in rows)
        if not ({r["method"] for r in rows if r["floor_error"] == fmin}
                & {r["method"] for r in rows if r["round_error"] == rmin}):
            changed += 1
    dq = [r for r in series if r["problem"] == "dahlquist"]
    dmin = min(r["floor_error"] for r in dq)
    tie = [r for r in dq if r["floor_error"] == dmin]
    _claim(len(tie) >= 2, "finding 2 says several methods tie exactly on dahlquist")
    _claim(abs(dmin - math.exp(-10)) < 1e-3 * math.exp(-10),
           "finding 2 says the dahlquist floor error is the whole reference value")
    ctx.update(
        n_methods=n_flip, fl_euler=_short(fl["error"]["euler"]),
        fl_rk4=_short(fl["error"]["rk4"]),
        fl_ratio=f"{fl['error']['rk4'] / fl['error']['euler']:.1f}",
        rd_rk4=_short(rd["error"]["rk4"]), rd_euler=_short(rd["error"]["euler"]),
        n_changed=changed, n_problems=len(problems),
        dq_tie=_join(sorted(r["method"] for r in tie)), dq_err=f"{dmin:.3g}",
        dq_worst=f"{max(r['round_error'] / r['floor_error'] for r in tie):,.0f}")

    # finding 3: the falsification sweep
    co = kf["crossover"]["numbers"]
    r4, h2 = co["methods"]["rk4"], co["methods"]["heun2"]
    th = co["thresholds"]
    _claim(r4["crossover_practical"] and h2["crossover_practical"]
           and h2["crossover_h"] < r4["crossover_h"],
           "finding 3 says both crossovers are practical and heun2's is at the smaller h")
    _claim(r4["q15_error_at_smallest_h"] > r4["min_q15_error"],
           "finding 3 says rk4's Q15 error climbs back as h shrinks")
    fast = [m["coefficient_fraction"]["m0plus_fast"] for m in co["methods"].values()]
    heun2_slow = h2["coefficient_fraction"]["m0plus_slow"]
    _claim(min(fast) >= th["proceed_fraction"] and heun2_slow < th["kill_fraction"],
           "finding 3 says fast fractions pass the proceed line and heun2 slow is under "
           "the kill line")
    sw = [r for r in kf["crossover"]["series"]["sweeps"]["rk4"]
          if isinstance(r.get("q15_error"), (int, float))]
    won4, of4 = co["rk4_wins_at_budget"]["floor"]["fraction"].split("/")
    _claim(int(of4) == len(problems), "finding 3 counts the same problems as finding 2")
    ctx.update(
        problem=co["problem"], rk4_min=_short(r4["min_q15_error"]),
        rk4_cross=_short(r4["crossover_h"]), h_small=_short(min(r["h"] for r in sw)),
        rk4_small=_short(r4["q15_error_at_smallest_h"]),
        heun2_cross=_short(h2["crossover_h"]), verdict=co["stored_verdict"],
        fals_verdict=co["stored_verdict"], fast_lo=_pct(min(fast), 0),
        fast_hi=_pct(max(fast), 0), proceed=_pct(th["proceed_fraction"], 0),
        heun2_slow=_pct(heun2_slow, 1), kill=_pct(th["kill_fraction"], 0),
        n_flip=n_flip, rk4_wins="none" if won4 == "0" else won4)

    # finding 4: the rc_thermal collapse
    rc = kf["rc_thermal_collapse"]["numbers"]
    pm = kf["rc_thermal_collapse"]["series"]["per_method"]
    by = {r["method"]: r for r in pm}
    lsbs = [r["final_state_lsbs_from_origin"] for r in pm]
    bdrc = rc["best_discovered_rc_thermal"]
    bd_rc = bdrc["error"]
    _claim((bdrc["stages"], bdrc["cycles"]) != (bd["stages"], bd["cycles"]),
           "finding 4 says the best discovered method on rc_thermal is not the finding 1 "
           "champion")
    _claim(by["rk38"]["round_error"] < rc["floor_error_min"] and bd_rc < rc["floor_error_min"],
           "finding 4 says rk38 under round-to-nearest and the best discovered method "
           "under floor both get under the floor")
    ctx.update(
        deriv_scale=_fr(rc["deriv_scale"]), lsb=f"{rc['lsb_physical']:.3g}",
        n_classical=len(pm), fe_min=f"{rc['floor_error_min']:.4f}",
        fe_max=f"{rc['floor_error_max']:.4f}",
        spread=_pct(rc["floor_error_spread_relative"], 1),
        lsb_lo=min(lsbs), lsb_hi=max(lsbs),
        euler_state=str(tuple(by["euler"]["final_state_q15"])),
        rk4_state=str(tuple(by["rk4"]["final_state_q15"])),
        ref_norm=f"{rc['reference_norm']:.4f}", t_end=f"{rc['t_end']:g}",
        rk38_rd=_short(by["rk38"]["round_error"]), bd_rc=_short(bd_rc),
        bdrc_stages=bdrc["stages"], bdrc_order=bdrc["order"], bdrc_cycles=bdrc["cycles"])

    # finding 5: phase 0
    p0 = kf["phase0_exhaustive"]["numbers"]
    opt, ru = p0["optimum"], p0["runner_up"]
    gap = abs(ru["heldout_error"] - opt["heldout_error"]) / opt["heldout_error"] * 100
    _claim(opt["name"] is None and ru["name"] is None,
           "finding 5 says neither phase-0 optimum is a textbook method")
    _claim(ru["heldout_error"] < anchor["heldout_error"],
           "finding 5 says both phase-0 optima beat every classical method")
    _claim(gap < 1, "finding 5 calls the two phase-0 optima a tie")
    ctx.update(
        lattice=p0["lattice_candidates"], valid=p0["valid_tableaus"],
        opt_a21=_fr(opt["a21"]), opt_b=_vec(opt["b"]), opt_err=_short(opt["heldout_error"]),
        opt_cyc=opt["cycles"], ru_a21=_fr(ru["a21"]), ru_err=_short(ru["heldout_error"]),
        gap=f"{gap:.2f}", n_anchors=len(n["classical_anchors"]),
        mid_rank=p0["midpoint_rank"], heun_rank=p0["heun2_rank"])

    # finding 6 and the matrix: the practical validation suite
    vv = vd["verdicts"]
    per = vv["per_problem"]
    prac = [p for p in vd["problems"] if not p.get("stiff")]
    stiff = [p for p in vd["problems"] if p.get("stiff")]
    names = {p["name"] for p in prac}
    rows = [(p["name"], per[p["name"]]) for p in prac if p["name"] in per]
    _claim(vv["practical_problems_compared"] == len(rows) == len(prac),
           "finding 6 compares every practical problem")
    _claim(vd.get("budget_cycles") == n["budget_cycles"],
           "finding 6 runs at the same budget as the archive")
    _claim(bd["stages"] == 3, "finding 6 calls the champion the three-stage method")
    wide_name, wide = min(rows, key=lambda nd: nd[1]["ratio_discovered_over_classical"])
    loss = "".join(T.F_VALIDATION_LOSS.format(
        p=name, c_name=d["best_classical"], c_err=_short(d["best_classical_q15_error"]),
        d_err=_short(d["best_discovered_q15_error"]),
        ratio=f"{d['ratio_discovered_over_classical']:.2f}")
        for name, d in rows if d.get("winner_kind") == "classical")
    res = [r for r in vd["results"] if r["problem"] in names
           and isinstance(r.get("q15_error"), (int, float))
           and isinstance(r.get("float_error"), (int, float)) and r["float_error"] > 0]
    sr = [p["stiffness_ratio"] for p in stiff]
    tp = bench["timing_protocol"]
    ctx.update(
        n_prac=len(prac), n_stiff=len(stiff),
        n_val_methods=len(vd["methods"]), domains=_join([p["domain"] for p in prac]),
        won=vv["practical_problems_won_by_discovered"],
        median=f"{vv['practical_median_ratio_discovered_over_classical']:.3f}",
        wide=wide_name, wide_d=_short(wide["best_discovered_q15_error"]),
        wide_c=_short(wide["best_classical_q15_error"]), wide_cname=wide["best_classical"],
        wide_x=f"{1 / wide['ratio_discovered_over_classical']:.1f}",
        champ_wins=sum(1 for _n, d in rows if d.get("winner") == bd["tableau_hash"]),
        loss_sentence=loss,
        float_x=f"{min(r['q15_error'] / r['float_error'] for r in res):,.0f}",
        max_q=max(r["max_abs_q"] for r in vd["results"]
                  if r["problem"] in names and isinstance(r.get("max_abs_q"), int)),
        repeats=tp["n_repeats"], warmup=tp["warmup"],
        sr_lo=f"{min(sr):,.0f}", sr_hi=f"{max(sr):,.0f}")

    # the matrix verdict and measured speed: the benchmark
    bv = bench["verdicts"]
    comp, low = bv["fixed_step_cells_compared"], bv["fixed_step_cells_where_q15_error_lower"]
    sp = bench["speedup"]
    srows = [r for r in sp["rows"] if r.get("status") == "ok"]
    keeps = [r["problem"] for r in srows if not r["champion_error_lower"]]
    _claim(sp["champion_error_lower_count"] == len(srows) - len(keeps),
           "the speed section counts the champion's error wins from the same rows")
    dev = max(abs(r["measured_ratio_rk4_over_champion"] / r["predicted_ratio_rk4_over_champion"]
                  - 1) for r in srows)
    ctx.update(
        lib_ratio=f"{bv['median_ratio_q15_over_library_at_matched_tolerance']:,.0f}",
        rk4_cells=f"all {comp}" if low == 0 else f"{comp - low} of {comp}",
        sp_n=len(srows), sp_won=sp["champion_error_lower_count"],
        maxdev=math.ceil(100 * dev), rk4_keeps=_join(keeps) or "none",
        sp_med=f"{sp['median_error_ratio_champion_over_rk4']:.2f}")

    # design decisions: the encourager calendar
    ctx.update(package_date=sg.encourager.PACKAGE_DATE.isoformat(),
               freeze_date=sg.encourager.FREEZE_DATE.isoformat())
    return ctx


# ----------------------------------------------------------------------------- page checks

# Estimated advance width per character, px, by svg text class; the default matches the
# rule of ~7 px/char at the 13px base size. Deliberately conservative.
_CHAR_PX = {"bt": 8.6, "bs": 7.35, "alab": 6.9, "dlab": 7.3, "lbl": 7.3, "mono": 7.9}
_SVG_RE = re.compile(r'<svg [^>]*viewBox="0 0 ([0-9.]+) ([0-9.]+)"[^>]*>(.*?)</svg>', re.S)
_TEXT_RE = re.compile(r"<text([^>]*)>(.*?)</text>", re.S)
_ATTR_RE = re.compile(r'([a-zA-Z-]+)="([^"]*)"')


def _audit_svg_text(name: str, html_text: str) -> list[str]:
    """Walk every SVG text node and flag any whose estimated extent leaves the viewBox."""
    import html as html_mod
    issues = []
    for sm in _SVG_RE.finditer(html_text):
        W, H = float(sm.group(1)), float(sm.group(2))
        for tm in _TEXT_RE.finditer(sm.group(3)):
            attrs = dict(_ATTR_RE.findall(tm.group(1)))
            content = html_mod.unescape(re.sub(r"<[^>]+>", "", tm.group(2)))
            if not content.strip():
                continue
            classes = (attrs.get("class") or "").split()
            px = max([_CHAR_PX.get(c, 0.0) for c in classes] + [0.0]) or 7.0
            m_sz = re.search(r"font-size:\s*([0-9.]+)px", attrs.get("style", ""))
            if m_sz:
                px = 0.54 * float(m_sz.group(1))
            width = len(content) * px
            try:
                x = float(attrs.get("x", "0"))
                y = float(attrs.get("y", "0"))
            except ValueError:
                continue
            anchor = attrs.get("text-anchor", "start")
            if "rotate(-90" in attrs.get("transform", ""):
                lo, hi, bound, axis = y - width / 2, y + width / 2, H, "y"
            else:
                if anchor == "middle":
                    lo, hi = x - width / 2, x + width / 2
                elif anchor == "end":
                    lo, hi = x - width, x
                else:
                    lo, hi = x, x + width
                bound, axis = W, "x"
                if y < -2 or y > H + 2:
                    issues.append(f"{name}: text {content[:44]!r} y={y:.0f} outside 0..{H:.0f}")
            if lo < -2 or hi > bound + 2:
                issues.append(f"{name}: text {content[:44]!r} {axis}-extent "
                              f"[{lo:.0f}, {hi:.0f}] outside 0..{bound:.0f}")
    return issues


_BALANCED_TAGS = ("div", "section", "figure", "svg", "details", "table", "ul", "ol", "dl")


def _check_balance(name: str, html_text: str) -> bool:
    # Script bodies hold markup as string fragments; counting those as page tags would
    # make the demo's chart builders look unbalanced. check_demo.js covers what they emit.
    markup = re.sub(r"<script>.*?</script>", "", html_text, flags=re.S)
    ok = True
    for tag in _BALANCED_TAGS:
        opens = len(re.findall(f"<{tag}[ >]", markup))
        closes = markup.count(f"</{tag}>")
        if opens != closes:
            print(f"WARN: {name}: <{tag}> open/close mismatch ({opens} vs {closes})")
            ok = False
    return ok


_HREF_RE = re.compile(r'href="([^"]*)"')
_ID_RE = re.compile(r'\bid="([^"]+)"')


def _check_links(pages: dict[str, str]) -> list[str]:
    """Every internal href names a page being written and an id on it. Every link into
    rk-findings names one of its current pages, and any fragment is an id that page is
    known to carry (_FINDINGS_FRAGMENTS). A retired name fails the build."""
    ids = {name: set(_ID_RE.findall(text)) for name, text in pages.items()}
    issues = []
    for name, text in pages.items():
        markup = re.sub(r"<script>.*?</script>", "", text, flags=re.S)
        for href in _HREF_RE.findall(markup):
            if href.startswith(LIVE_URL):
                page, _, frag = href[len(LIVE_URL):].partition("#")
                if page not in _FINDINGS_PAGES:
                    issues.append(f"{name}: {href} is not a current findings page")
                elif frag and frag not in _FINDINGS_FRAGMENTS.get(page, ()):
                    issues.append(f"{name}: {href} names an id that "
                                  f"{page or 'index.html'} is not known to carry "
                                  "(see _FINDINGS_FRAGMENTS)")
            elif re.match(r"[a-z]+:", href):
                continue
            else:
                page, _, frag = href.partition("#")
                target = page or name
                if target not in pages:
                    issues.append(f"{name}: {href} names no page on this site")
                elif frag and frag not in ids[target]:
                    issues.append(f"{name}: {href} names no id on {target}")
    return issues


def _check_incoming(pages: dict[str, str]) -> list[str]:
    """The mirror of _check_links, for the other direction. The findings methodology page
    deep-links section ids on architecture.html; those links are read from the rendered
    article rather than from its source, because methodology.py builds them inside
    f-strings. Renaming a section here then fails this build instead of leaving a dead
    link on the other site."""
    wanted = set(re.findall(re.escape(meth._ARCH) + r"#([\w-]+)", meth._body()))
    if not wanted:
        return ["rk_harness.methodology renders no link into the architecture page: the "
                "parse broke, so this check is protecting nothing"]
    have = set(_ID_RE.findall(pages["architecture.html"]))
    return [f'architecture.html has no id "{i}", which the findings methodology page links'
            for i in sorted(wanted - have)]


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


def _anchor_bars_live() -> str:
    """sitegen's anchor chart, with every relative link pointed at the live findings site
    (its glossary links are relative to rk-findings, not to this site)."""
    return re.sub(r'href="(?![a-z]+:|#)([^"]*)"',
                  lambda m: f'href="{LIVE_URL}{m.group(1)}"', sg._anchor_bars())


def _index_page(ctx: dict, demo: dict) -> str:
    spine = '<div class="spine">' + "".join(
        f'<section><span class="k">{sg._esc(k)}</span><h2>{sg._esc(h)}</h2>{_t(t, **ctx)}'
        f'<a class="more" href="{href}">{sg._esc(link)} &rarr;</a></section>'
        for k, h, t, href, link in T.SPINE) + "</div>"
    classes = '<div class="cards">' + "".join(
        f'<div class="card klass k-{cls}"><div class="k">{sg._esc(status)}</div>'
        f'<div class="v">{cls}</div><p class="n">{sg._esc(text)}</p>'
        f'<p class="go"><a href="{LIVE_URL}{cls}.html">{cls} methods on rk-findings '
        "&#8599;</a></p></div>" for cls, status, text in T.CLASSES) + "</div>"
    chips = _chips([(ctx["archive_n"], "verified tableaus archived"),
                    (ctx["cycles_n"], "search cycles"),
                    (str(ctx["cells_total"]), "grid cells occupied"),
                    (f"{TESTS_TOTAL:,}", "tests in the suite")])
    repos = '<div class="grid-cards">' + "".join(
        f'<a class="gcard" href="{url}"><div class="t">{sg._esc(name)} &#8599;</div>'
        f'<div class="d">{sg._esc(desc)}</div></a>' for name, url, desc in T.REPOS) + "</div>"
    body = [_t(T.HERO_LEAD), _DEMO.hero_body(len(demo["methods"]), demo["budget_cycles"]),
            spine, '<h2 id="classes">Three method classes</h2>', _t(T.CLASSES_LEAD), classes,
            '<h2 id="scale">What it took</h2>', chips,
            '<h2 id="source">The source</h2>', _t(T.SOURCE_LEAD), repos]
    hero = _hero_data(demo)
    return _page(T.HERO_TITLE, "\n".join(body), "index.html", T.HERO_SUB,
                 head_extra="<style>" + _DEMO.HERO_CSS + "</style>\n",
                 body_end=("<script>window.__RKFLIP__="
                           + json.dumps(hero, separators=(",", ":"))
                           + ";</script>\n<script>" + _DEMO.HERO_JS + "</script>\n"))


def _results_page(ctx: dict, kf: dict, vd: dict, bench: dict, records, orders) -> str:
    charts = {"efficiency": [frontier_chart(kf), grid_coverage_chart(records, orders)],
              "floor-flip": [flip_slope_chart(kf),
                             _fold("Per problem: floor against round-to-nearest",
                                   flip_problem_chart(kf))],
              "crossover": [crossover_chart(kf)],
              "rc-thermal": [rc_chart(kf)],
              "phase0": [phase0_chart(kf)],
              "validation": [validation_chart(vd)]}
    toc = ([("anchor", T.ANCHOR_TITLE)]
           + [(slug, _t(title, **ctx)) for slug, title, _i, _p in T.FINDINGS]
           + [("matrix", T.MATRIX_TITLE), ("speed", T.SPEED_TITLE),
              ("protocol", T.PROTOCOL_TITLE), ("limits", T.LIMITS_TITLE),
              ("others", T.OTHERS_TITLE)])
    body = [_t(T.HEADLINE_VERDICT, **ctx),
            f'<p class="note">{sg._esc(_t(T.RESULTS_SCOPE, **ctx))}</p>',
            '<ul class="toc">' + "".join(f'<li><a href="#{s}">{sg._esc(t)}</a></li>'
                                         for s, t in toc) + "</ul>",
            f'<h2 id="anchor">{sg._esc(T.ANCHOR_TITLE)}</h2>',
            '<div class="two"><div>' + _t(T.ANCHOR_TEXT, **ctx) + "</div>"
            '<div class="panel">' + _anchor_bars_live() + "</div></div>"]
    for i, (slug, title, intro, interp) in enumerate(T.FINDINGS, 1):
        body.append(_finding(slug, i, _t(title, **ctx), _t(intro, **ctx), charts[slug],
                             _t(interp, **ctx)))
    body += [f'<h2 id="matrix">{sg._esc(T.MATRIX_TITLE)}</h2>', _t(T.MATRIX_LEAD, **ctx),
             heldout_chart(kf, vd), _t(T.MATRIX_VERDICT, **ctx),
             '<details class="fold"><summary>The full matrix: every method, every column, '
             "and where each column comes from</summary><div>"
             + method_matrix(vd, bench, kf, _t(T.MATRIX_FOOTNOTES, **ctx)) + "</div></details>",
             f'<h2 id="speed">{sg._esc(T.SPEED_TITLE)}</h2>', _t(T.SPEED_INTRO, **ctx),
             speedup_chart(bench), _t(T.SPEED_INTERP, **ctx),
             f'<h2 id="protocol">{sg._esc(T.PROTOCOL_TITLE)}</h2>', _t(T.PROTOCOL, **ctx),
             f'<h2 id="limits">{sg._esc(T.LIMITS_TITLE)}</h2>', _t(T.LIMITS, **ctx),
             f'<h2 id="others">{sg._esc(T.OTHERS_TITLE)}</h2>', _t(T.OTHERS, **ctx)]
    return _page("Key findings", "\n".join(body), "results.html",
                 _t(T.RESULTS_SUB, date=SNAPSHOT_DATE))


def _architecture_page(ctx: dict) -> str:
    tiers = ('<details class="fold"><summary>What each test tier covers</summary><div>'
             '<div class="scroll"><table><tr><th>tier</th><th class="num">tests</th>'
             "<th>covers</th></tr>" + "".join(
                 f'<tr><td>{t}</td><td class="num">{n:,}</td><td>{sg._esc(d)}</td></tr>'
                 for t, n, d in SUITE_TIERS) + "</table></div></div></details>")
    body = [_marker_sprite(), _t(T.ARCH_LEAD),
            '<h2 id="repos">The repositories</h2>', repo_diagram(), _t(T.ARCH_REPOS),
            '<h2 id="boundaries">Trust boundaries</h2>', system_diagram(),
            _t(T.ARCH_BOUNDARIES),
            '<h2 id="loop">The cycle loop</h2>', cycle_diagram(), _t(T.ARCH_CYCLE),
            '<h2 id="lanes">Three classes, taking turns</h2>', _t(T.ARCH_LANES),
            '<h2 id="verify">Verification, in order</h2>', pipeline_diagram(),
            _t(T.ARCH_GATE, **ctx),
            '<h2 id="arithmetic">Arithmetic, exactly</h2>', _t(T.ARCH_ARITH, **ctx),
            '<h2 id="costmodel">The cost model</h2>',
            _t(T.ARCH_COSTMODEL, table=_cost_table()),
            '<h2 id="candidates">Where candidates come from</h2>',
            _t(T.ARCH_CANDIDATES, **ctx),
            '<h2 id="archive">The archive</h2>', _t(T.ARCH_ARCHIVE),
            '<h2 id="outer">The outer loop</h2>', _t(T.ARCH_OUTER),
            '<h2 id="host">The host layer</h2>', _t(T.ARCH_HOST),
            '<h2 id="tests">Testing</h2>', _t(T.ARCH_TESTS, **ctx), tiers,
            '<h3 id="preflight">The pre-flight, run as a program</h3>', _t(T.ARCH_PREFLIGHT),
            '<h2 id="repro">Reproducibility</h2>', _t(T.ARCH_REPRO)]
    return _page("Architecture", "\n".join(body), "architecture.html", T.ARCH_SUB)


def _decisions_page(ctx: dict) -> str:
    _claim(REVISED_DECISIONS <= {slug for slug, _t_, _o, _a in T.DECISIONS},
           "every decision tagged as revised exists on the page")
    lead = _t(T.DECISIONS_LEAD, n=len(T.DECISIONS), n_rev=len(REVISED_DECISIONS))
    body = [f'<p class="note">{lead}</p>']
    for slug, title, orig, asbuilt in T.DECISIONS:
        tag = ('<span class="tag tag-changed">revised in build</span>'
               if slug in REVISED_DECISIONS
               else '<span class="tag tag-kept">held up</span>')
        body.append(f'<div class="decision" id="{slug}">'
                    f'<h3><a href="#{slug}" style="color:inherit;text-decoration:none">'
                    f"{title}</a>{tag}</h3>"
                    f'<div class="orig"><strong>Before the build:</strong> '
                    f"{_t(orig, **ctx)}</div>"
                    f'<div class="asbuilt"><strong>As built:</strong> '
                    f"{_t(asbuilt, **ctx)}</div></div>")
    body += ['<h2 id="cuts">What was deliberately cut</h2>', _t(T.CUTS),
             '<h2 id="prior-art">Known prior art, and where the gap is</h2>', _t(T.PRIOR_ART)]
    return _page("Design decisions", "\n".join(body), "design-decisions.html",
                 T.DECISIONS_SUB)


def _demo_page(demo: dict) -> str:
    cross = demo["_meta"]["crosscheck"]
    body = _DEMO.body(LIVE_URL, len(demo["methods"]), demo["budget_cycles"],
                      len(demo["expected"]), cross["comparisons"], cross["max_rel_diff"])
    return _page("Run the arithmetic yourself", body, "demo.html",
                 "The Q15 integrator running in your browser, checked against the "
                 "evaluator that scored the archive.",
                 head_extra="<style>" + _DEMO.DEMO_CSS + "</style>\n",
                 body_end=("<script>window.__RKDEMO__="
                           + json.dumps(demo, separators=(",", ":"))
                           + ";</script>\n<script>" + _DEMO.DEMO_JS + "</script>\n"))


def build() -> None:
    global TESTS_TOTAL, SUITE_TIERS, GATE_TESTS, SNAPSHOT_DATE
    SUITE_TIERS, TESTS_TOTAL = _collect_suite()
    GATE_TESTS = _gate_count()
    print(f"suite: {TESTS_TOTAL:,} tests collected across {len(SUITE_TIERS)} tiers; "
          f"start gate {GATE_TESTS}")
    records = archive.read_all()
    if not records:
        raise SystemExit("no archive records: refusing to build a snapshot of nothing")
    SNAPSHOT_DATE = timefmt.fmt_ct(max(r.timestamp for r in records))[:10]
    print(f"snapshot date derived from the newest archive record: {SNAPSHOT_DATE}")
    kf, vd, bench, demo = _kf_load(), _validation_load(), _bench_load(), _demo_load()
    kf_n = kf["efficiency"]["numbers"]["archive_records"]
    if kf_n != len(records):
        print(f"NOTE: key_findings.json covers {kf_n:,} records and the archive now holds "
              f"{len(records):,}; rerun tools/key_findings.py to refresh the analysis")
    print(f"computing symbolic orders for the grid chart ({len(records):,} records)...")
    orders = [archive.record_order(r) for r in records]
    ctx = _results_ctx(kf, vd, bench, _eff_ctx(kf, records, orders))
    ctx.update(gate=GATE_TESTS, tests=TESTS_TOTAL, tiers=len(SUITE_TIERS),
               demo_cases=len(demo["expected"]))

    pages = {"index.html": _index_page(ctx, demo),
             "architecture.html": _architecture_page(ctx),
             "design-decisions.html": _decisions_page(ctx),
             "results.html": _results_page(ctx, kf, vd, bench, records, orders),
             "demo.html": _demo_page(demo)}
    assert list(pages) == [href for href, _l in _NAV]

    # The page checks run before anything is written, so a failed check leaves docs/ as it
    # was. The two node checks need the written pages and run last, in _check_scripts().
    problems: list[str] = []
    for name, text in pages.items():
        if not _check_balance(name, text):
            problems.append(f"{name}: unbalanced tags (see WARN lines)")
        if name != "demo.html":          # the demo's charts are built at view time
            problems += [f"SVG-AUDIT: {i}" for i in _audit_svg_text(name, text)]
    problems += [f"LINK: {i}" for i in _check_links(pages)]
    problems += [f"LINK: {i}" for i in _check_incoming(pages)]
    for line in problems:
        print(line)
    if problems:
        raise SystemExit("page checks failed; nothing was written")

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    for name, text in pages.items():
        (DOCS / name).write_text(text, encoding="utf-8")
        print("wrote", name, f"({len(text.encode('utf-8')) / 1024:.0f} KB, "
              f"{len(_SVG_RE.findall(text))} charts)")
    # Pages the site no longer has would otherwise keep being served by GitHub Pages.
    for name in _RETIRED:
        if (DOCS / name).exists():
            (DOCS / name).unlink()
            print("removed retired page", name)
    stale = DOCS / "findings"
    if stale.exists():
        shutil.rmtree(stale)
        print("removed the stale docs/findings snapshot; the nav links to the live site")

    _check_scripts()


if __name__ == "__main__":
    import os
    # A Windows console defaults to cp1252, which cannot print the arrows and fractions
    # some check messages quote.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("RK_WORK_DIR", str(WS / "rk-work"))
    build()
