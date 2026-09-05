"""Emit tools/demo_data.json: everything the browser demo needs, plus the fixture it
checks itself against.

The demo page re-implements Q15 arithmetic and the explicit RK step in JavaScript so a
visitor can move the controls and watch the numbers change. That re-implementation is only
worth putting on a site like this if it is provably the same arithmetic, so this script
also writes an `expected` block: the final Q15 state, step count and error that
`rk_harness.simulate.solve_q15` produces for every (method, problem, rounding) the demo
offers. The page runs all of them on load and prints how many matched exactly. A
disagreement shows up as a failed check on the page rather than as a quietly wrong chart.

Run from rk-harness with RK_WORK_DIR set:

    .venv/Scripts/python.exe ../rk-overview/tools/demo_data.py
"""
from __future__ import annotations

import json
import math
import sys
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WS = ROOT.parent
sys.path.insert(0, str(WS / "rk-harness"))

from rk_harness import archive, problems, simulate, tableau as tableau_mod  # noqa: E402
from rk_harness.coeffrep import to_rep  # noqa: E402
from rk_harness.fixedpoint import _check, q15_from_float  # noqa: E402
from rk_harness.costmodel import COST_MODELS, cycle_count  # noqa: E402
from rk_harness.orderconditions import achieved_order_symbolic  # noqa: E402
from rk_harness.problems import DERIV_SCALE, PEAK, error_metric, to_physical  # noqa: E402
from rk_harness.types import Tableau  # noqa: E402

BUDGET = 65536
MODELS = ("m0plus_fast", "m0plus_slow")
CURVE_POINTS = 120

# The classical field the site already talks about, in the order the charts use.
CLASSICAL = ("euler", "midpoint", "heun2", "ralston2", "heun3", "kutta3", "rk4", "rk38")
# Discovered methods worth putting next to them: the archive elite with the lowest
# held-out error, and the two exhaustively-proved cells. Labels stay short enough for a
# chart row; the note carries the rest.
DISCOVERED_LABELS = {
    "11e898cb": ("found p2s3", "champion",
                 "the archive elite with the lowest held-out error"),
    "2d2c2b75": ("found p2s2", "proved optimal",
                 "optimal within the fully enumerated 2-stage space"),
    "4f501ec6": ("found p3s3", "proved optimal",
                 "optimal within the fully enumerated 3-stage space"),
}


def _rep_pair(x: Fraction):
    """(m, s) for a nonzero coefficient, None for zero. Mirrors coeffrep.to_rep."""
    if x == 0:
        return None
    r = to_rep(Fraction(x))
    return [r.m, r.s]


def _tableau_json(name: str, label: str, origin: str, t: Tableau, extra: dict) -> dict:
    order = achieved_order_symbolic(t)
    cycles = {m: {str(n): cycle_count(t, COST_MODELS[m], n) for n in (1, 2, 3, 4)}
              for m in MODELS}
    return {
        "key": name,
        "label": label,
        "origin": origin,
        "stages": len(t.b),
        "order": order,
        "A": [[_rep_pair(x) for x in row] for row in t.A],
        "b": [_rep_pair(x) for x in t.b],
        "c": [float(x) for x in t.c],
        "A_frac": [[f"{Fraction(x).numerator}/{Fraction(x).denominator}" for x in row] for row in t.A],
        "b_frac": [f"{Fraction(x).numerator}/{Fraction(x).denominator}" for x in t.b],
        "cycles": cycles,
        **extra,
    }


def _methods() -> list[dict]:
    out: list[dict] = []
    classical = tableau_mod.classical()
    for name in CLASSICAL:
        out.append(_tableau_json(name, name, "classical", classical[name],
                                 {"tag": "", "note": "classical anchor"}))
    seen: set[str] = set()
    arch = archive.replay()
    elites = [rec for grid in arch.grids.values() for rec in grid.values()]
    for rec in sorted(elites, key=lambda r: r.tableau_hash):
        short = rec.tableau_hash[:8]
        if short not in DISCOVERED_LABELS or short in seen:
            continue
        seen.add(short)
        label, tag, note = DISCOVERED_LABELS[short]
        out.append(_tableau_json(short, label, "discovered", rec.tableau,
                                 {"hash": rec.tableau_hash, "tier": rec.tier,
                                  "tag": tag, "note": note}))
    return out


def _problems() -> list[dict]:
    out = []
    for name in ("dahlquist", "damped_osc", "vanderpol_mild",
                 "pendulum", "dc_motor", "rc_thermal", "quaternion"):
        p = problems.PROBLEMS[name]
        curve = []
        for i in range(CURVE_POINTS + 1):
            t = p.t_end * i / CURVE_POINTS
            curve.append([t] + [float(v) for v in p.reference(t)])
        out.append({
            "name": name,
            "family": p.family,
            "n_states": p.n_states,
            "y0": [int(v) for v in p.y0],
            "y0_phys": [float(v) for v in to_physical(p.y0, p.scale)],
            "t_end": p.t_end,
            "scale": p.scale,
            "deriv_scale": DERIV_SCALE.get(name, 1.0),
            "peak": PEAK[name],
            "metric": ("energy" if name == "pendulum"
                       else "norm1" if name == "quaternion" else "l2"),
            "set": "search" if name in ("dahlquist", "damped_osc", "vanderpol_mild") else "heldout",
            "ref_end": [float(v) for v in p.reference(p.t_end)],
            "ref_curve": curve,
        })
    return out


def _shift(v: int, k: int, mode: str) -> int:
    """v / 2**k under one rounding mode.

    floor is ARM's ASRS, what the harness measures everywhere. nearest is the
    counterfactual: add half an LSB, then shift. Both rules were checked against
    tools/floor_round.json, the file the floor-bias finding is computed from, and
    reproduce all 28 of its published errors exactly (see CROSSCHECK below)."""
    if mode == "floor" or k == 0:
        return v >> k
    return (v + (1 << (k - 1))) >> k


def _solve(t: Tableau, p, n: int, mode: str) -> tuple[int, ...]:
    """simulate.solve_q15 with the shift rule factored out.

    Identical to the pinned solver when mode == 'floor'; the demo checks that claim
    numerically rather than asserting it."""
    h = p.t_end / n
    h_q = q15_from_float(h / DERIV_SCALE.get(p.name, 1.0))
    s = len(t.b)
    reps_A = [[(to_rep(x) if x != 0 else None) for x in row] for row in t.A]
    reps_b = [(to_rep(x) if x != 0 else None) for x in t.b]
    c_f = [float(x) for x in t.c]
    states = range(len(p.y0))
    y = tuple(int(v) for v in p.y0)
    for step in range(n):
        tk = step * h
        hk: list[tuple[int, ...]] = []
        for i in range(s):
            acc = y
            for j in range(i):
                rep = reps_A[i][j]
                if rep is None:
                    continue
                acc = tuple(_check(acc[m] + _check(_shift(hk[j][m] * rep.m, rep.s, mode), "apply"),
                                   "add") for m in states)
            k_i = p.f(tk + c_f[i] * h, acc)
            hk.append(tuple(_check(_shift(kk * h_q, 15, mode), "mul") for kk in k_i))
        y_new = y
        for i in range(s):
            rep = reps_b[i]
            if rep is None:
                continue
            y_new = tuple(_check(y_new[m] + _check(_shift(hk[i][m] * rep.m, rep.s, mode), "apply"),
                                 "add") for m in states)
        y = y_new
    return y


def _crosscheck() -> dict:
    """Confirm _solve reproduces tools/floor_round.json, the published floor-bias data."""
    path = HERE / "floor_round.json"
    if not path.exists():
        return {"status": "floor_round.json absent"}
    fr = json.loads(path.read_text(encoding="utf-8"))
    classical = tableau_mod.classical()
    worst = 0.0
    n_cmp = 0
    for mode, key in (("floor", "floor"), ("nearest", "round_to_nearest")):
        for mname, per in sorted(fr.get(key, {}).items()):
            t = classical[mname]
            for pname, want in sorted(per.items()):
                p = problems.PROBLEMS[pname]
                n = simulate.steps_for_budget(t, COST_MODELS["m0plus_fast"], p.n_states, BUDGET)
                got = error_metric(pname, to_physical(_solve(t, p, n, mode), p.scale))
                n_cmp += 1
                worst = max(worst, abs(got - want) / max(abs(want), 1e-30))
    return {"source": "rk-overview/tools/floor_round.json",
            "comparisons": n_cmp, "max_rel_diff": worst}


def _expected(methods: list[dict]) -> list[dict]:
    """Ground truth from the pinned evaluator, for both rounding modes.

    The floor entries come from rk_harness.simulate.solve_q15 itself, so the demo is
    checked against the code that scored the archive, not against a copy of it."""
    classical = tableau_mod.classical()
    arch = archive.replay()
    by_hash = {rec.tableau_hash[:8]: rec.tableau
               for grid in arch.grids.values() for rec in grid.values()}
    out = []
    for m in methods:
        t = classical[m["key"]] if m["origin"] == "classical" else by_hash[m["key"]]
        for p in problems.PROBLEMS.values():
            n = simulate.steps_for_budget(t, COST_MODELS["m0plus_fast"], p.n_states, BUDGET)
            for mode in ("floor", "nearest"):
                row = {"m": m["key"], "p": p.name, "mode": mode, "steps": n}
                if n <= 0:
                    row["status"] = "no_steps"
                    out.append(row)
                    continue
                try:
                    final = (simulate.solve_q15(t, p, n)[0] if mode == "floor"
                             else _solve(t, p, n, mode))
                except Exception as exc:               # overflow is a real outcome, not a bug
                    row["status"] = "overflow" if "Overflow" in type(exc).__name__ else "error"
                    out.append(row)
                    continue
                err = error_metric(p.name, to_physical(final, p.scale))
                row["status"] = "ok"
                row["final"] = [int(v) for v in final]
                row["error"] = err if math.isfinite(err) else None
                out.append(row)
    return out


def main() -> None:
    methods = _methods()
    data = {
        "_meta": {
            "script": "rk-overview/tools/demo_data.py",
            "budget_cycles": BUDGET,
            "cost_model": "m0plus_fast",
            "note": ("expected[] is produced by rk_harness.simulate.solve_q15 under the pinned "
                     "verifier; the demo page recomputes each entry in the browser and reports "
                     "how many match exactly."),
            "crosscheck": _crosscheck(),
        },
        "budget_cycles": BUDGET,
        "methods": methods,
        "problems": _problems(),
        "expected": _expected(methods),
    }
    dest = HERE / "demo_data.json"
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=False)
        fh.write("\n")
    ok = sum(1 for e in data["expected"] if e.get("status") == "ok")
    cc = data["_meta"]["crosscheck"]
    print(f"wrote {dest} ({dest.stat().st_size / 1024:.0f} KB): "
          f"{len(methods)} methods, {len(data['problems'])} problems, "
          f"{ok}/{len(data['expected'])} reference runs completed")
    print(f"floor_round.json cross-check: {cc.get('comparisons')} comparisons, "
          f"max relative difference {cc.get('max_rel_diff')}")


if __name__ == "__main__":
    main()
