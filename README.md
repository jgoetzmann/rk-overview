# rk-overview

The human-maintained explainer for the rk project (quantization-aware Runge-Kutta search).
The companion repo rk-findings carries the authoritative, machine-generated numbers; this site
carries the narrative: what the project is, how the system is built, every design decision and
what the build did to it, run-level charts, and an interactive demo of the Q15 integrator.

Site: https://jgoetzmann.github.io/rk-overview/

## Pages

Nine pages in two nav tiers. The first tier is the reading path (overview, run it, key
findings, trade-offs); the second is the record behind it (architecture, methodology, design
decisions, research tracks, literature). The findings site is linked live rather than copied:
a frozen copy used to live under docs/findings/ and drifted from the real thing within days.

`index.html` opens on the result rather than describing it: a slope chart ranking eleven
methods under floor rounding against round-to-nearest, with a problem selector and per-method
hover. It ships about 3 KB of data reduced out of `demo_data.json`, not the demo's 120 KB, so
both pages rank the same numbers. Under it the page runs Problem, Approach, Result, Verify, and
links the three repositories so any number can be traced to the code that produced it.

`demo.html` is the full version. It re-implements `rk_harness.fixedpoint` and
`rk_harness.simulate.solve_q15` in the browser so a visitor can rank the whole method field at
one cycle budget, flip the rounding mode and watch the order change, and read a Pareto frontier
that is recomputed from the coefficients on every click.

## Regenerating

Numbers first, then the demo fixture, then the pages:

    ..\rk-harness\.venv\Scripts\python.exe tools\key_findings.py   # analysis from the archive
    ..\rk-harness\.venv\Scripts\python.exe tools\demo_data.py      # tableaus, problems, fixture
    ..\rk-harness\.venv\Scripts\python.exe tools\generate.py       # write docs/

`generate.py` fails the build on unbalanced tags, on any SVG text that leaves its viewBox, and
on either JavaScript page failing its headless check. Both checks need node:

    node tools\check_demo.js     # docs/demo.html
    node tools\check_hero.js     # the landing widget in docs/index.html

`check_demo.js` loads the published page, drives all 154 control combinations and recomputes
every fixture case in JavaScript, comparing the final int16 state bit for bit against
`rk_harness.simulate.solve_q15`. `check_hero.js` drives every problem and hover and re-derives
the ranking independently, so a chart that mis-sorts fails the build; reversing the widget's
sort comparator makes it report 0 matched rows and exit 1.

## Numbers that must not drift

Counts appearing in prose on more than one page (occupied cells, cells won, archive size) are
formatted in from `key_findings.json` by `generate._eff_ctx`, never typed into `pages_text.py`.
They were typed by hand once and drifted a cycle apart, so the index and the key-findings page
disagreed with each other.

The test count and the tier list come from `pytest --collect-only` at build time
(`generate._collect_suite`, about 2 seconds), for the same reason: the hardcoded `TESTS_TOTAL`
went 25 short the first time someone added a test file. Only the per-tier descriptions are
hand-written, in `_SUITE_DESC`. **A new `tests/test_tN_*.py` with no entry there fails the
build** with a message asking for one, so a new tier gets described rather than silently
omitted.

Because of that, this build is deliberately not byte-reproducible across suite or archive
changes: it reads live inputs. The findings site is the one with the byte-determinism
guarantee.

DESIGN.md is the original pre-build decision record, kept verbatim; the design-decisions page
annotates it against the as-built system.
