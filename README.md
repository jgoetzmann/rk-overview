# rk-overview

The hand-written explainer for the rk project, an unattended search for Runge-Kutta
integrators that do well in Q15 fixed point (int16, floor multiply) on a Cortex-M0+
cycle model. The machine-generated numbers live in
[rk-findings](https://github.com/jgoetzmann/rk-findings); this site explains what the
project is, how it is built, the decisions behind it and what it found, and it runs the
Q15 integrator in the browser.

- Site: https://jgoetzmann.github.io/rk-overview/
- Live findings: https://jgoetzmann.github.io/rk-findings/

## The repositories

Four public repositories. Every number on this site traces through them in one direction:
the harness computes it, the run data records it, the findings site publishes it, and this
repository explains it.

| Repo | What it holds | Written by |
| --- | --- | --- |
| [rk-harness](https://github.com/jgoetzmann/rk-harness) | The package the container runs: the hash-pinned verifier, cost model and evaluator, the search, the site generator, and the tests that gate all of it. | people |
| [rk-work](https://github.com/jgoetzmann/rk-work) | Run data: the append-only archive, the hypothesis ledger, and the validation and benchmark outputs. | the container, per cycle |
| [rk-findings](https://github.com/jgoetzmann/rk-findings) ([site](https://jgoetzmann.github.io/rk-findings/)) | The numbers site, rebuilt every cycle with no human in the loop. Deterministic and JavaScript-free. | the container, per cycle |
| [rk-overview](https://github.com/jgoetzmann/rk-overview) | This repository: the explainer pages, the interactive demo, and the tools that build both from the run archive. | people, on demand |

A fifth, private repository holds the scripts and configuration that run all of this on
one machine. It is not linked here.

rk-findings is written by a container that cannot edit its own scorer, which is what makes
its numbers worth anything. This repository is written by hand and says so. Where the two
disagree, the machine-generated one is right and this one is stale.

## Pages

Five pages in one nav row, followed by a link to the live findings site.

| Page | What it holds |
| --- | --- |
| `index.html` (overview) | The ranking widget (eleven methods, floor against round-to-nearest), the problem, approach, result and verify steps, the three method classes with links to their findings pages, the scale of the run, and the four repositories. |
| `architecture.html` | The system as built: repository and trust-boundary diagrams, the cycle loop and how it rotates the three classes (`#lanes`), verification in order (`#verify`), arithmetic, the cost model, where candidates come from, the archive, the outer loop, the host layer, tests (`#tests`) and reproducibility (`#repro`). The findings methodology page deep-links `#arithmetic`, `#costmodel`, `#archive`, `#candidates`, `#outer`, `#verify`, `#tests` and `#repro`, so those ids must stay, and the build fails if one of them goes missing. |
| `design-decisions.html` | The pre-build decisions from DESIGN.md, each with what the build did to it, the deliberate cuts and how two of them were revisited, and prior art. |
| `results.html` (key findings) | The anchor result, six findings with their charts, discovered against classical against library methods (`#matrix`), measured speed (`#speed`), how the numbers were made (`#protocol`), the limits, and a pointer to the implicit and adaptive class pages on the findings site. |
| `demo.html` | A line-for-line port of `rk_harness.fixedpoint` and `rk_harness.simulate.solve_q15` that ranks the method field at one cycle budget, flips the rounding mode, and recomputes a Pareto frontier on every click. |

The build deletes the retired pages (`tradeoffs.html`, `methodology.html`, `tracks.html`,
`literature.html`) and any old `docs/findings/` copy, so GitHub Pages stops serving them.

Links into the findings site name one of its seven current pages, and a fragment only
where that page is known to carry the id: `validation.html#speed` and `#falsification`,
`hypotheses.html#interpretation` and `#literature`, and `methodology.html#costmodel`,
`#ledger`, `#glossary` or a glossary term (the term ids are read from
`rk_harness.sitegen._GLOSSARY`).

Two pages carry JavaScript: `demo.html` and the ranking widget on `index.html`, which ships
about 3 KB reduced out of `demo_data.json` so that both pages rank the same numbers.

## Regenerating

Numbers first, then the demo fixture, then the pages. Run from this directory; all three
default `RK_WORK_DIR` to `..\rk-work`:

    ..\rk-harness\.venv\Scripts\python.exe tools\key_findings.py   # analysis from the archive
    ..\rk-harness\.venv\Scripts\python.exe tools\demo_data.py      # tableaus, problems, fixture
    ..\rk-harness\.venv\Scripts\python.exe tools\generate.py       # write docs/

Regenerate `demo_data.json` whenever the archive elites or the problem set move.

## What the build checks

`generate.py` checks every page before it writes any, and stops the build on:

- unbalanced tags on any page;
- SVG text that leaves its viewBox;
- a broken link: an internal href must name a page and an id that exist, and a link into
  the findings site must follow the rule above;
- a dropped id: every architecture id the findings methodology page deep-links must still
  exist here. The links are read from `rk_harness.methodology`, so this side of the pair
  is checked as well as the side above;
- a pattern sentence the data no longer supports (for example "floor puts euler first"),
  so the prose is rewritten instead of going quietly wrong.

After writing the pages it runs a headless check on each JavaScript page and fails the
build if either fails. The checks need node on the PATH. Without it the build prints a
WARN, skips them and still writes the pages, so run them by hand:

    node tools\check_demo.js     # docs/demo.html
    node tools\check_hero.js     # the ranking widget in docs/index.html

`check_demo.js` loads the published page, drives every control and recomputes every
fixture case in JavaScript, comparing the final int16 state bit for bit against
`rk_harness.simulate.solve_q15`. `check_hero.js` drives every problem and hover and
re-derives the ranking independently, so a chart that mis-sorts fails the build.

## Numbers that must not drift

No number from the run is typed into `pages_text.py`. Every string there is a template,
and `generate.py` fills it from `tools/key_findings.json`, `rk-work/validation/results.json`,
`rk-work/benchmark/results.json`, the archive, the pinned cost model, `demo_data.json` and
the test collection. Counts that appear on more than one page (occupied cells, cells won,
archive size) come from `generate._eff_ctx`, so the pages cannot disagree.

The test count and the tier list come from `pytest --collect-only` at build time
(`generate._collect_suite`), and the gate size from `rk-harness/tests/golden_gate.txt`.
Only the per-tier descriptions are hand-written, in `_SUITE_DESC`. A new
`tests/test_tN_*.py` with no entry there fails the build, so a new tier gets described
rather than silently left out.

Because it reads live inputs, this build is not byte-reproducible across suite or archive
changes. The findings site is the one with the byte-determinism guarantee.

DESIGN.md is the original pre-build decision record, kept verbatim; the design-decisions
page annotates it against the system as built.
