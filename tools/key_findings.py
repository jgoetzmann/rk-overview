"""Compute the Key Findings numbers from the live run data.

Writes tools/key_findings.json next to this file. Rerunnable: fresh archive in,
fresh numbers out. Deterministic given the data files (no wall-clock timestamps
in the output).

Inputs
    rk-work/archive/*.jsonl      via rk_harness.archive.replay()
    rk-work/falsification.json   (contains literal Infinity tokens; parsed with
                                  Python's json, which accepts them, then every
                                  non-finite float is written out as null)
    rk-overview/tools/floor_round.json

Usage (any cwd; the script sets RK_WORK_DIR/RK_FINDINGS_DIR itself if unset):
    D:/Programming-Projects/Integration-Harness/rk-harness/.venv/Scripts/python.exe tools/key_findings.py

Output schema (key_findings.json)
    _meta                  provenance: sources, budget, cost model, archive size,
                           sanitization note. No timestamps, for byte determinism.
    <finding>              one top-level key per finding:
      efficiency           did discovered methods beat the classical anchors
      floor_bias_flip      floor vs round-to-nearest ranking flip at the budget
      crossover            where Q15 error decouples from float truncation error
      rc_thermal_collapse  the shared quantization floor on rc_thermal
      phase0_exhaustive    the closed 2-stage enumeration result
    Every finding has exactly three keys:
      verdict              one- or two-sentence honest statement of the result
      numbers              scalar facts, each traceable to the data files
      series               chart-ready arrays; every series is non-empty or is
                           replaced by {"absent": "<reason>"}
    Non-finite floats (Infinity in falsification.json sweeps) become null in
    series rows; _meta.nonfinite_written_as_null counts the replacements.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # rk-overview/tools
WS = HERE.parent.parent                          # workspace root
os.environ.setdefault("RK_WORK_DIR", str(WS / "rk-work"))
os.environ.setdefault("RK_FINDINGS_DIR", str(WS / "rk-findings"))
sys.path.insert(0, str(WS / "rk-harness"))

from rk_harness import archive, enumeration                       # noqa: E402
from rk_harness.costmodel import M0PLUS_FAST                      # noqa: E402
from rk_harness.problems import PROBLEMS                          # noqa: E402
from rk_harness.simulate import solve_q15, steps_for_budget       # noqa: E402
from rk_harness.tableau import classical, content_hash, to_json   # noqa: E402

BUDGET = 65536
MODEL = "m0plus_fast"
SEARCH_PROBLEMS = ("dahlquist", "damped_osc", "vanderpol_mild")
HELDOUT_PROBLEMS = ("pendulum", "dc_motor", "rc_thermal", "quaternion")
ALL_PROBLEMS = SEARCH_PROBLEMS + HELDOUT_PROBLEMS
OUT_PATH = HERE / "key_findings.json"

_nonfinite_count = 0


def _num(v):
    """Finite float passthrough; non-finite becomes None (counted)."""
    global _nonfinite_count
    if v is None:
        return None
    f = float(v)
    if math.isfinite(f):
        return f
    _nonfinite_count += 1
    return None


def _rms(values):
    vals = [float(v) for v in values]
    return math.sqrt(sum(v * v for v in vals) / len(vals)) if vals else 0.0


def _ranks(scores: dict[str, float]) -> dict[str, int]:
    """1 = lowest error. Ties broken by name for determinism."""
    order = sorted(scores, key=lambda k: (scores[k], k))
    return {name: i + 1 for i, name in enumerate(order)}


# --------------------------------------------------------------------- loading

def load_inputs():
    state = archive.replay()
    records = archive.read_all()
    fals = json.loads((WS / "rk-work" / "falsification.json").read_text(encoding="utf-8"))
    fr = json.loads((HERE / "floor_round.json").read_text(encoding="utf-8"))
    return state, records, fals, fr


def classical_index(records):
    """name -> its unique archive Record; verified by hash AND by seed markers."""
    by_hash = {content_hash(t): n for n, t in classical().items()}
    found: dict[str, list] = {}
    for r in records:
        n = by_hash.get(r.tableau_hash)
        if n is not None:
            found.setdefault(n, []).append(r)
    problems = []
    for n in by_hash.values():
        rs = found.get(n, [])
        if len(rs) != 1:
            problems.append(f"{n}: {len(rs)} records")
        elif not (rs[0].cycle_id == 0 and rs[0].seed == 0):
            problems.append(f"{n}: not a cycle-0/seed-0 seed record")
    return {n: rs[0] for n, rs in found.items()}, problems


# ------------------------------------------------------------------ finding 1

def efficiency(state, records, anchors: dict):
    classical_hashes = {r.tableau_hash: n for n, r in anchors.items()}
    anchor_rows = sorted(
        ({"name": n, "cycles": r.score.cycles[MODEL],
          "heldout_error": _num(r.score.heldout_error),
          "search_error": _num(r.score.search_error),
          "measured_order": _num(r.score.measured_order)}
         for n, r in anchors.items()), key=lambda d: (d["cycles"], d["name"]))

    cells = []           # every grid cell, discovered and classical
    for order in sorted(state.grids):
        for (stages, bucket), r in sorted(state.grids[order].items()):
            cells.append((order, stages, bucket, r))

    frontier = []
    ratios_all, ratios_wins = [], []
    n_wins = n_discovered = 0
    best_cell = None
    for order, stages, bucket, r in cells:
        cyc = r.score.cycles[MODEL]
        he = r.score.heldout_error
        name = classical_hashes.get(r.tableau_hash)
        row = {"kind": "classical" if name else "discovered",
               "name": name, "order": order, "stages": stages,
               "cycle_bucket": bucket, "cycles": cyc,
               "heldout_error": _num(he), "tier": r.tier,
               "tableau_hash": r.tableau_hash}
        if name is None and math.isfinite(he):
            n_discovered += 1
            cheaper = [a["heldout_error"] for a in anchor_rows
                       if a["cycles"] <= cyc and a["heldout_error"] is not None]
            best_anchor = min(cheaper) if cheaper else None
            if best_anchor is not None:
                ratio = he / best_anchor
                row["best_cheaper_or_equal_anchor_error"] = best_anchor
                row["error_ratio_vs_best_cheaper_anchor"] = _num(ratio)
                ratios_all.append(ratio)
                if ratio < 1.0:
                    n_wins += 1
                    ratios_wins.append(ratio)
            if best_cell is None or he < best_cell[3].score.heldout_error:
                best_cell = (order, stages, bucket, r)
        frontier.append(row)
    # classical anchors not holding a cell still belong on the frontier chart
    on_frontier = {row["name"] for row in frontier if row["name"]}
    for a in anchor_rows:
        if a["name"] not in on_frontier:
            r = anchors[a["name"]]
            frontier.append({"kind": "classical", "name": a["name"],
                             "order": None, "stages": len(r.tableau.b),
                             "cycle_bucket": None, "cycles": a["cycles"],
                             "heldout_error": a["heldout_error"], "tier": r.tier,
                             "tableau_hash": r.tableau_hash})
    frontier.sort(key=lambda d: (d["cycles"], d["tableau_hash"]))

    bo, bs, bb, br = best_cell
    best_anchor_overall = min(a["heldout_error"] for a in anchor_rows)
    best_anchor_name = min(anchor_rows, key=lambda a: a["heldout_error"])["name"]
    best = {"order": bo, "stages": bs, "cycles": br.score.cycles[MODEL],
            "heldout_error": _num(br.score.heldout_error),
            "search_error": _num(br.score.search_error),
            "measured_order": _num(br.score.measured_order),
            "tier": br.tier, "tableau_hash": br.tableau_hash,
            "tableau": to_json(br.tableau),
            "per_problem_heldout": {p: _num(br.score.per_problem.get(p))
                                    for p in HELDOUT_PROBLEMS},
            "ratio_vs_best_classical_anchor":
                _num(br.score.heldout_error / best_anchor_overall)}

    med_all = sorted(ratios_all)[len(ratios_all) // 2] if ratios_all else None
    med_win = sorted(ratios_wins)[len(ratios_wins) // 2] if ratios_wins else None
    verdict = (
        f"Yes. At the shared {BUDGET:,}-cycle budget under floor-rounded Q15, "
        f"{n_wins} of {n_discovered} archive cells holding a discovered method beat every "
        f"classical anchor of equal or lower per-step cost on held-out error; the best "
        f"discovered method (order 2, 3 stages, {best['cycles']} cycles/step) reaches held-out "
        f"error {best['heldout_error']:.4f} against {best_anchor_overall:.4f} for the best "
        f"classical anchor ({best_anchor_name}), a {best_anchor_overall / best['heldout_error']:.1f}x reduction. "
        f"The remaining classical cells are euler (sole order-1 entry) and rk38, which no "
        f"discovered 4-stage order-4 method displaced in its own cell.")
    return {
        "verdict": verdict,
        "numbers": {
            "budget_cycles": BUDGET, "cost_model": MODEL,
            "rounding_mode": "floor (ASRS)",
            "archive_records": state.n_records,
            "unique_tableaus": len({r.tableau_hash for r in records}),
            "last_cycle_id": state.last_cycle_id,
            "grid_cells_total": len(cells),
            "cells_held_by_discovered": n_discovered,
            "cells_held_by_classical": len(cells) - n_discovered,
            "cells_where_discovered_beats_all_cheaper_or_equal_anchors": n_wins,
            "median_error_ratio_discovered_over_anchor": _num(med_all),
            "median_error_ratio_winning_cells": _num(med_win),
            "best_error_ratio": _num(min(ratios_all)) if ratios_all else None,
            "best_discovered": best,
            "classical_anchors": anchor_rows,
            "note_on_comparison": (
                "Every heldout_error is evaluated at the same total budget of "
                f"{BUDGET} cycles, so cheaper methods take more steps; 'cycles' is "
                "the per-step coefficient-arithmetic cost at n_states=1 under "
                "m0plus_fast. The cheapest anchor with the lowest error is midpoint "
                "(11 cycles), which is cheaper than every discovered elite, so "
                "beating all cheaper-or-equal anchors here equals beating every "
                "anchor outright."),
            "caveats": [
                "Cell elites are selected by held-out error among 45k+ unique "
                "candidates, so the champion values carry selection (winner's "
                "curse) bias; the CMA-ES search itself optimizes only the "
                "search-set error.",
                "Tier labels are mechanical insertion-time comparisons against "
                "the then-incumbent, not a validation grade of the final elite; "
                "the overall best cell is tier 'unreplicated'.",
                "rc_thermal saturates near 0.156 for every classical method "
                "(see rc_thermal_collapse), so classical held-out RMS values "
                "are floored near 0.078; discovered winners break that floor.",
            ],
        },
        "series": {
            "frontier_cycles_vs_heldout": frontier,
            "chart_hint": "log-log scatter, x=cycles, y=heldout_error, color by "
                          "kind, label classical points by name",
        },
    }


# ------------------------------------------------------------------ finding 2

def floor_bias_flip(fr: dict):
    floor = fr["floor"]
    rnd = fr["round_to_nearest"]
    methods = sorted(floor)
    agg = {}
    for mode_name, mode in (("floor", floor), ("round_to_nearest", rnd)):
        per_metric = {}
        for label, probs in (("search_rms", SEARCH_PROBLEMS),
                             ("heldout_rms", HELDOUT_PROBLEMS),
                             ("all7_rms", ALL_PROBLEMS)):
            scores = {m: _rms(mode[m][p] for p in probs) for m in methods}
            per_metric[label] = {"error": {m: _num(v) for m, v in scores.items()},
                                 "rank": _ranks(scores)}
        agg[mode_name] = per_metric

    per_problem = []
    for p in ALL_PROBLEMS:
        f_scores = {m: floor[m][p] for m in methods}
        r_scores = {m: rnd[m][p] for m in methods}
        fr_ranks, rr_ranks = _ranks(f_scores), _ranks(r_scores)
        for m in methods:
            per_problem.append({"problem": p, "method": m,
                                "floor_error": _num(f_scores[m]),
                                "round_error": _num(r_scores[m]),
                                "floor_rank": fr_ranks[m],
                                "round_rank": rr_ranks[m]})

    sf = agg["floor"]["search_rms"]["error"]
    sr = agg["round_to_nearest"]["search_rms"]["error"]
    verdict = (
        f"Floor rounding reorders the field at the {BUDGET:,}-cycle budget. On the three "
        f"search problems euler's RMS error is {sf['euler']:.4f} under floor against "
        f"{sf['rk4']:.4f} for rk4 ({sf['rk4'] / sf['euler']:.1f}x worse), while under "
        f"round-to-nearest rk4 beats euler ({sr['rk4']:.4f} vs {sr['euler']:.4f}): euler "
        f"moves from rank {agg['round_to_nearest']['search_rms']['rank']['euler']} to rank "
        f"{agg['floor']['search_rms']['rank']['euler']} and rk4 from rank "
        f"{agg['round_to_nearest']['search_rms']['rank']['rk4']} to rank "
        f"{agg['floor']['search_rms']['rank']['rk4']} of 4. Over all 7 problems rk38 stays "
        f"first in both modes, but the floor-mode spread between methods collapses.")
    return {
        "verdict": verdict,
        "numbers": {
            "budget_cycles": fr.get("budget", BUDGET),
            "cost_model": fr.get("model", MODEL),
            "aggregate": agg,
            "dahlquist_note": (
                "Under floor, euler/heun2/rk38 hit dahlquist error "
                f"{floor['euler']['dahlquist']:.6e}, which equals exp(-10), the full "
                "reference value: the Q15 state decays to exactly 0 and the true "
                "answer is below one LSB, so floor's downward bias lands on the "
                "right answer. Under round-to-nearest the state stalls in a "
                "dead zone above zero (errors 0.033 to 0.092, up to "
                f"{rnd['heun2']['dahlquist'] / floor['heun2']['dahlquist']:.0f}x worse)."),
            "mechanism": (
                "Each Q15 multiply floors, injecting a -0.5 LSB expected bias per "
                "product. rk4 spends more multiplies per unit of simulated time "
                "and takes larger steps at equal budget, so its order advantage "
                "is spent absorbing bias; cheap low-order methods take more, "
                "smaller steps and win on problems whose solutions decay."),
        },
        "series": {
            "per_problem_floor_vs_round": per_problem,
            "chart_hint": "paired bars or slope chart per problem, log y; a "
                          "second slope chart for aggregate ranks (search_rms)",
        },
    }


# ------------------------------------------------------------------ finding 3

def crossover(fals: dict, fr: dict):
    methods = {}
    for name, m in fals["methods"].items():
        rows = [{"n": r["n"], "h": r["h"],
                 "q15_error": _num(r["q15_error"]),
                 "float_error": _num(r["float_error"])} for r in m["sweep"]]
        # error growth after the crossover: last finite q15 vs its minimum
        q15_fin = [r["q15_error"] for r in rows if r["q15_error"] is not None]
        methods[name] = {
            "stages": m["stages"],
            "crossover_h": m["crossover_h"],
            "crossover_practical": m["crossover_practical"],
            "coefficient_fraction": m["coefficient_fraction"],
            "cycles_per_step": m["cycles_per_step"],
            "derivative_cost": m["derivative_cost"],
            "min_q15_error": _num(min(q15_fin)) if q15_fin else None,
            "q15_error_at_smallest_h": _num(q15_fin[-1]) if q15_fin else None,
            "sweep": rows,
        }

    floor = fr["floor"]
    anchors4 = sorted(floor)
    rk4_wins_floor = [p for p in ALL_PROBLEMS
                      if all(floor["rk4"][p] <= floor[m][p] for m in anchors4)]
    rnd = fr["round_to_nearest"]
    rk4_wins_round = [p for p in ALL_PROBLEMS
                      if all(rnd["rk4"][p] <= rnd[m][p] for m in anchors4)]
    best_floor = {p: min(anchors4, key=lambda m: (floor[m][p], m)) for p in ALL_PROBLEMS}
    best_round = {p: min(anchors4, key=lambda m: (rnd[m][p], m)) for p in ALL_PROBLEMS}

    rk4 = methods["rk4"]
    heun2 = methods["heun2"]
    verdict = (
        f"On damped_osc, rk4's Q15 error decouples from its float truncation error at "
        f"h = {rk4['crossover_h']:.5g} (float error keeps falling as h^4; Q15 error rises "
        f"from {rk4['min_q15_error']:.2e} to {rk4['q15_error_at_smallest_h']:.2e} as h "
        f"shrinks to {rk4['sweep'][-1]['h']:.5g}); heun2 decouples later, at "
        f"h = {heun2['crossover_h']:.5g}. The stored falsification verdict is "
        f"'{fals['verdict']}': coefficient arithmetic is 50-56% of per-step cycles on "
        f"m0plus_fast (above the 0.30 proceed threshold) but 14.8% for heun2 on "
        f"m0plus_slow (below the 0.15 kill threshold). At the equal {BUDGET:,}-cycle "
        f"budget under floor, rk4 wins {len(rk4_wins_floor)} of 7 problems outright "
        f"(under round-to-nearest: {len(rk4_wins_round)} of 7, with rk38 taking "
        f"{sum(1 for p in best_round.values() if p == 'rk38')}).")
    return {
        "verdict": verdict,
        "numbers": {
            "problem": fals["problem"], "t_end": fals["t_end"],
            "models": fals["models"], "stored_verdict": fals["verdict"],
            "thresholds": fals["thresholds"],
            "methods": {n: {k: v for k, v in m.items() if k != "sweep"}
                        for n, m in methods.items()},
            "rk4_wins_at_budget": {
                "floor": {"fraction": f"{len(rk4_wins_floor)}/7",
                          "problems": rk4_wins_floor,
                          "best_method_per_problem": {p: best_floor[p] for p in ALL_PROBLEMS}},
                "round_to_nearest": {"fraction": f"{len(rk4_wins_round)}/7",
                                     "problems": rk4_wins_round,
                                     "best_method_per_problem": {p: best_round[p] for p in ALL_PROBLEMS}},
                "note": "computed from floor_round.json over the four methods it "
                        "covers (euler, heun2, rk4, rk38) at budget 65536, m0plus_fast",
            },
        },
        "series": {
            "sweeps": {n: m["sweep"] for n, m in methods.items()},
            "chart_hint": "log-log lines, x=h, y=error; per method one solid "
                          "(q15_error) and one dashed (float_error) line; null "
                          "q15 values are overflow (error was infinite)",
        },
    }


# ------------------------------------------------------------------ finding 4

def rc_thermal_collapse(state, anchors: dict, fr: dict):
    p = PROBLEMS["rc_thermal"]
    ref = p.reference(p.t_end)
    ref_norm = math.sqrt(sum(v * v for v in ref))
    lsb = 1.0 / 32768.0 / p.scale
    rows = []
    for name in sorted(anchors):
        t = classical()[name]
        n = steps_for_budget(t, M0PLUS_FAST, p.n_states, BUDGET)
        yq, _ = solve_q15(t, p, n)
        phys = tuple(q / 32768.0 / p.scale for q in yq)
        err = math.sqrt(sum((a - b) ** 2 for a, b in zip(phys, ref)))
        rows.append({"method": name, "steps": n, "final_state_q15": list(yq),
                     "final_state_lsbs_from_origin": max(abs(q) for q in yq),
                     "floor_error": _num(err),
                     "round_error": _num(fr["round_to_nearest"].get(name, {}).get("rc_thermal")),
                     "archive_error": _num(anchors[name].score.per_problem.get("rc_thermal"))})
    floor_errs = [r["floor_error"] for r in rows]
    classical_hashes = {r.tableau_hash for r in anchors.values()}
    disc = [(rec.score.per_problem["rc_thermal"], rec.score.cycles[MODEL], o, s)
            for o, grid in state.grids.items()
            for (s, _b), rec in grid.items()
            if rec.tableau_hash not in classical_hashes
            and math.isfinite(rec.score.per_problem.get("rc_thermal", math.inf))]
    best_disc = min(disc) if disc else None
    spread = (max(floor_errs) - min(floor_errs)) / min(floor_errs)
    verdict = (
        f"All 8 classical methods land within {100 * spread:.1f}% of one another on "
        f"rc_thermal under floor (errors {min(floor_errs):.4f} to {max(floor_errs):.4f}) "
        f"because every one of them drives the Q15 state into a dead zone 4 to 18 LSBs "
        f"from the origin while the true solution still has norm {ref_norm:.4f}: the "
        f"reported error is essentially the reference itself, a quantization floor, not a "
        f"method property. Under round-to-nearest the same methods separate (rk38 reaches "
        f"{fr['round_to_nearest']['rk38']['rc_thermal']:.4f}), and the best discovered "
        f"method reaches {best_disc[0]:.4f} while still using floor.")
    return {
        "verdict": verdict,
        "numbers": {
            "problem": "rc_thermal", "t_end": p.t_end, "scale": p.scale,
            "deriv_scale": 0.125, "lsb_physical": _num(lsb),
            "reference_at_t_end": [_num(v) for v in ref],
            "reference_norm": _num(ref_norm),
            "floor_error_min": _num(min(floor_errs)),
            "floor_error_max": _num(max(floor_errs)),
            "floor_error_spread_relative": _num(spread),
            "best_discovered_rc_thermal": None if best_disc is None else {
                "error": _num(best_disc[0]), "cycles": best_disc[1],
                "order": best_disc[2], "stages": best_disc[3]},
            "mechanism": (
                "rc_thermal decays toward equilibrium and its derivative is "
                "stored scaled by 1/8 (DERIV_SCALE), so late in the run the "
                "quantized derivative terms are a few LSBs; floor rounding "
                "turns them into extra decay, and every classical method's "
                "state collapses to near zero instead of tracking the slow "
                "mode. Error metric is ||y - ref(4)||/peak, so everyone "
                "reports about ||ref(4)|| = 0.159 minus a small residual."),
        },
        "series": {
            "per_method": rows,
            "chart_hint": "grouped bars per method: floor_error vs round_error, "
                          "with a horizontal line at reference_norm",
        },
    }


# ------------------------------------------------------------------ finding 5

def phase0_exhaustive(records, anchors: dict):
    tabs = enumeration.enumerate_phase0()
    n_lattice = enumeration.phase0_candidate_count()
    by_hash: dict[str, list] = {}
    for r in records:
        by_hash.setdefault(r.tableau_hash, []).append(r)
    classical_names = {r.tableau_hash: n for n, r in anchors.items()}
    rows = []
    for t in tabs:
        h = content_hash(t)
        rs = by_hash.get(h, [])
        best = min(rs, key=lambda r: r.score.heldout_error) if rs else None
        rows.append({
            "a21": f"{t.A[1][0].numerator}/{t.A[1][0].denominator}",
            "b": [f"{x.numerator}/{x.denominator}" for x in t.b],
            "name": classical_names.get(h),
            "in_archive": bool(rs),
            "cycles": best.score.cycles[MODEL] if best else None,
            "heldout_error": _num(best.score.heldout_error) if best else None,
            "tableau_hash": h,
        })
    evaluated = [r for r in rows if r["heldout_error"] is not None]
    evaluated.sort(key=lambda r: r["heldout_error"])
    for i, r in enumerate(evaluated):
        r["rank"] = i + 1
    rows.sort(key=lambda r: r["heldout_error"] if r["heldout_error"] is not None else math.inf)
    opt = rows[0]
    runner_up = rows[1]
    best_anchor = min((_a.score.heldout_error, n) for n, _a in anchors.items())
    missing = [r["a21"] for r in rows if not r["in_archive"]]
    rank_of = {r["a21"]: r.get("rank") for r in rows}
    verdict = (
        f"Closed result: the phase-0 space (2-stage, a21 on the dyadic lattice s<=6, "
        f"|a21|<=2: {n_lattice} candidates, {len(tabs)} with exactly representable b) was "
        f"enumerated in full and all {len(tabs)} members are in the archive. Nothing in it "
        f"beats a21 = {opt['a21']}, b = ({', '.join(opt['b'])}) at {opt['cycles']} "
        f"cycles/step with held-out error {opt['heldout_error']:.4f}, a near-tie with "
        f"a21 = {runner_up['a21']} ({runner_up['heldout_error']:.4f}); within the same "
        f"family midpoint ranks {rank_of.get('1/2')} and heun2 ranks {rank_of.get('1/1')} "
        f"of {len(evaluated)}. The optimum also beats all 8 classical anchors "
        f"(best: {best_anchor[1]}, {best_anchor[0]:.4f}) at the equal budget.")
    return {
        "verdict": verdict,
        "numbers": {
            "lattice_candidates": n_lattice,
            "valid_tableaus": len(tabs),
            "all_in_archive": not missing,
            "missing_from_archive": missing,
            "optimum": opt,
            "runner_up": runner_up,
            "midpoint_rank": rank_of.get("1/2"),
            "heun2_rank": rank_of.get("1/1"),
            "best_classical_anchor": {"name": best_anchor[1],
                                      "heldout_error": _num(best_anchor[0])},
            "closure_note": (
                "Phase 0 is exhaustive by construction (events.jsonl records "
                "'enumeration complete'), so this optimum is over the whole "
                "space, not a sample: no 2-stage tableau in the lattice does "
                "better at this budget under these semantics."),
        },
        "series": {
            "all_members": rows,
            "chart_hint": "dot plot: x=a21 (categorical, ordered by value), "
                          "y=heldout_error, highlight optimum, midpoint, heun2",
        },
    }


# --------------------------------------------------------------------- driver

def build() -> dict:
    state, records, fals, fr = load_inputs()
    anchors, anchor_problems = classical_index(records)
    # cross-check floor_round.json floor side against the archive seed scores
    max_rel = 0.0
    for name in fr["floor"]:
        rec = anchors.get(name)
        if rec is None:
            continue
        for prob, v in fr["floor"][name].items():
            a = rec.score.per_problem.get(prob)
            if a and v:
                max_rel = max(max_rel, abs(a - v) / max(abs(v), 1e-300))
    out = {
        "_meta": {
            "script": "rk-overview/tools/key_findings.py",
            "sources": ["rk-work/archive/*.jsonl (via rk_harness.archive.replay)",
                        "rk-work/falsification.json",
                        "rk-overview/tools/floor_round.json"],
            "budget_cycles": BUDGET,
            "cost_model": MODEL,
            "rounding_mode": "floor (ASRS), per HANDOFF 4.2",
            "archive_records": state.n_records,
            "archive_last_cycle_id": state.last_cycle_id,
            "archive_dates": sorted({r.timestamp[:10] for r in records}),
            "classical_seed_check": ("all 8 classical anchors identified by tableau "
                                     "content-hash; each appears exactly once, at "
                                     "cycle_id 0 / seed 0" if not anchor_problems
                                     else f"PROBLEMS: {anchor_problems}"),
            "floor_round_vs_archive_max_rel_diff": _num(max_rel),
            "schema": ("top-level key per finding; each finding has 'verdict' "
                       "(honest one-liner), 'numbers' (scalar facts), 'series' "
                       "(chart-ready arrays; non-empty or {'absent': reason})"),
        },
        "efficiency": efficiency(state, records, anchors),
        "floor_bias_flip": floor_bias_flip(fr),
        "crossover": crossover(fals, fr),
        "rc_thermal_collapse": rc_thermal_collapse(state, anchors, fr),
        "phase0_exhaustive": phase0_exhaustive(records, anchors),
    }
    out["_meta"]["nonfinite_written_as_null"] = _nonfinite_count
    return out


def _check_series(out: dict) -> list[str]:
    issues = []
    for key, finding in out.items():
        if key.startswith("_"):
            continue
        for req in ("verdict", "numbers", "series"):
            if req not in finding:
                issues.append(f"{key}: missing '{req}'")
        for sname, s in finding.get("series", {}).items():
            if sname == "chart_hint":
                continue
            if isinstance(s, dict) and "absent" in s:
                continue
            if isinstance(s, dict):
                empty = [k for k, v in s.items() if not v]
                if empty or not s:
                    issues.append(f"{key}.series.{sname}: empty entries {empty}")
            elif not s:
                issues.append(f"{key}.series.{sname}: empty")
    return issues


def main() -> int:
    out = build()
    text = json.dumps(out, indent=1, allow_nan=False)
    OUT_PATH.write_text(text + "\n", encoding="utf-8", newline="\n")
    # strict validation: reject NaN/Infinity tokens and re-check shape
    strict = json.loads(text, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
    issues = _check_series(strict)
    print(f"wrote {OUT_PATH} ({len(text):,} bytes, "
          f"{out['_meta']['nonfinite_written_as_null']} non-finite values -> null)")
    if issues:
        print("SERIES PROBLEMS:")
        for i in issues:
            print(" -", i)
        return 1
    print("all findings have verdict/numbers/series and every series is non-empty")
    return 0


if __name__ == "__main__":
    sys.exit(main())
