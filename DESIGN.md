# DESIGN — rationale and overview

Short by intent. Every entry is a decision that was made deliberately and could
reasonably have gone the other way.

---

## The harness in one picture

```
        ┌─────────────┐
        │ Orchestrator│  wakes on schedule, sets budgets
        └──────┬──────┘
     ┌─────────┼─────────┐
     ▼         ▼         ▼
 Research  Search core  Visualizer
 (LLM,     (CMA-ES,     (read-only,
  cheap)    no LLM)      generates site)
     │         │              ▲
     │         ▼              │
     │   ┌──────────┐         │
     │   │ Verifier │  no LLM, read-only mount
     │   └────┬─────┘
     └────────┼──────────────┘
              ▼
      ┌───────────────┐
      │ Shared archive│  append-only JSONL, MAP-Elites grids
      └───────────────┘
```

The verifier sits between candidate generation and the archive and contains no
model calls. Everything upstream may be wrong; nothing wrong gets recorded.

---

## Decisions

**The problem is quantization, not coefficient prettiness.**
The original premise — that multiplying by 1/3 is expensive — is false in
floating point, because `h·b` constant-folds at compile time and 1/3 and 0.25
cost the same instruction. The premise survives only in fixed-point on an
FPU-less MCU, where a power-of-two coefficient becomes a shift instead of a
multiply. Scope narrowed accordingly.

**Order ≥ 3 admits no all-dyadic tableau.**
Dyadic rationals are closed under + and ×. The order-3 condition is Σbᵢcᵢ² =
1/3, which is not dyadic. So the objective is not "find dyadic methods" but
"minimize non-dyadic multiplies subject to order p." Encoded as verifier reject
code `DYADIC_IMPOSSIBLE` so the search never wastes a cycle on an empty region.

**Static cycle counting, not simulation, not hardware.**
The integrator inner loop is branchless straight-line code, so summing ISA cycle
costs from the disassembly gives an *exact* count — better than a simulator,
faster, and a genuine WCET figure. It also means host CPU contention cannot
corrupt the primary metric, which is what makes passive background running safe.

**Cortex-M0+ primary, AVR secondary, two M0+ multiplier variants.**
M0+ has no FPU, no divide, no long multiply, so fixed-point is forced. Running
the same tableaus under a 1-cycle and a 32-cycle multiplier model costs nothing
extra and turns "hardware-aware" from a slogan into a demonstrated effect if the
ranking changes.

**Q15, wrapping, overflow as a rejection.**
Q31 loses on M0+ because there is no `UMULL` and a Q31 multiply must be
synthesized. Saturation loses because there is no `SSAT`, so saturating means a
compare-and-branch, destroying branchlessness and exact counting. Making
overflow a verifier rejection at 2× amplitude turns a runtime cost into a
property of the method.

**Classical optimizer in the inner loop, LLM in the outer loop.**
FunSearch and AlphaEvolve work because program space has no gradients. A 6-
parameter tableau space does. CMA-ES beats an LLM mutation operator here
decisively and for free. The LLM decides *what* to search and interprets *what
came back* — research partner, not sampler. This also removes the quota problem
almost entirely.

**Search/held-out split, enforced structurally.**
The optimizer has no code path that reads `HELDOUT_SET`. Overfitting to the test
suite is the failure mode that would silently invalidate three months of work,
and the held-out gap is a first-class dashboard metric precisely so it cannot
rot unnoticed.

**MAP-Elites, one grid per order.**
Descriptors are stage count and cycle-cost bucket. This yields a *table* of
results rather than a single champion, which is both more useful and what the
findings site wants to display.

**Equal cycle budget, never equal step size.**
A 2-stage method gets twice the steps of a 4-stage method for the same cost.
Comparing at equal h is the most common route to a wrong conclusion here.

**Fixed resource limits plus a pause watchdog, not dynamic allocation.**
Resizing every minute fights WSL2's fixed VM ceiling and unreliable memory
updates. Low `cpu-shares` plus `docker pause` on contention achieves the actual
goal — stay out of the way — in about forty lines instead of an allocation
manager. No GPU: this workload has no GPU component.

**Credentials outside the container; harness mounted read-only.**
If the agent can write the verifier, the shortest path to a high score is
editing the scorer, and it will look like a plausible refactor in the diff. The
PAT is scoped to `rk-work` and `rk-findings` only, and the 403 on `rk-harness`
is an acceptance test rather than an assumption.

**Auto-publish numbers, never claims.**
The site emits values and mechanical captions with mechanically-assigned
confidence tiers. An auto-published wrong result should be a wrong number in a
table, not a public claim requiring retraction.

**The encourager may change direction but not stop.**
Before Nov 20 it cannot return `FINISH`, only redirect, widen, hypothesize, or
advance phase. Set-and-forget systems without an explicit calendar run until the
operator gets bored, which is the worst possible ending.

**Falsification experiment on day 2, before the harness exists.**
If coefficient arithmetic turns out to be swamped by the derivative evaluation,
the whole thesis is dead. Finding that out in week one leaves you with a
reusable benchmark. Finding it out in month three leaves you with nothing.

---

## What was deliberately cut

Adaptive step size and Newton-iteration implicit methods: both break the
execution-time certificate that hard real-time requires, so they are wrong for
the target application, not merely out of budget. Order > 4 and linear multistep:
no reason to expect the quantization effect is larger there, and they multiply
the search space. Rosenbrock methods are the natural *second* project — fixed
operation count, handles stiffness — but not part of this one.

---

## Known prior art, and where the gap is

RKTK (Zhang, 2019) already does unstructured numerical search over Butcher
order conditions and holds a stage-count record at order 10. Numerical search
over tableaus is not the contribution. What that line of work optimizes is
order, stages, and error constants. **Nobody optimizes against a hardware cost
model, and nobody evaluates in fixed-point.** That is the gap this project
occupies, and it is narrow enough to actually finish.
