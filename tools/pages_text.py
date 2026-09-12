"""Prose for the rk-overview pages, kept apart from the chart and page machinery.

rk-findings is the machine-generated record and these pages explain it. Where the two
disagree, this site is the stale one.

Every string here is a str.format template. generate.py fills {live} (the findings site
root) and the named counts from tools/key_findings.json, rk-work/validation/results.json,
rk-work/benchmark/results.json, the archive, the pinned cost model and the test
collection. No number from the run is typed into this file: hand-typed counts are how
the index and the key-findings page once disagreed. Where a sentence states a pattern
rather than a number (euler first under floor, say), generate.py checks the pattern
against the data and fails the build if it no longer holds. A literal brace would need
doubling.

One home per fact:
  index             hero widget, the four-step spine, the three method classes, scale
                    chips, the source repositories
  architecture      repositories, boundaries, the loop and its three classes,
                    verification, arithmetic, cost model, search, archive, outer loop,
                    host, tests, reproducibility
  design-decisions  the pre-build decisions and what the build did to each, the cuts,
                    prior art
  results           the anchor result, six findings, the method matrix, measured speed,
                    how the numbers were made, limits
  demo              the Q15 integrator in the browser (its prose is in demo_page.py)
A page that needs a fact from another page links to it instead of repeating it.
"""

LIVE_URL = "https://jgoetzmann.github.io/rk-findings/"

# One quiet line per page. {date} is the snapshot date, US Central.
FOOTER = (
    "Built by rk-overview/tools/generate.py from the run archive, data as of {date} (US "
    "Central). This site is a snapshot; rk-findings carries the live numbers. Text drafted "
    "with Claude, edited and owned by the author.")

# ------------------------------------------------------------------------------ index

HERO_TITLE = "Searching for Runge-Kutta methods that survive fixed-point arithmetic"
HERO_SUB = "An unattended search for Runge-Kutta coefficients, scored by code it cannot edit."

HERO_LEAD = """
<p class="herolead">Textbook Runge-Kutta coefficients are tuned for exact arithmetic. A
microcontroller without an FPU rounds every multiply down, so the error always leans the
same way. This project is an unattended search for the coefficients that do best after
that rounding. Each candidate is scored on its end-to-end error in Q15 at a fixed
Cortex-M0+ cycle budget.</p>
"""

# Problem, approach, result, verify. One claim and one link per block; anything that
# needs a second paragraph belongs on the page the block links to.
SPINE = (
    ("problem", "Textbook coefficients assume arithmetic the chip does not have",
     "<p>Runge-Kutta tableaus are derived by cancelling truncation error in exact "
     "arithmetic. A Cortex-M0+ has no FPU, so the state lives in Q15 and every multiply "
     "ends in a right shift that rounds down, biasing each product by half an LSB in the "
     "same direction. None of the prior tableau searches that the project's literature "
     "loop surveyed models this rounding.</p>",
     "results.html#crossover", "the premise, tested before the search"),
    ("approach", "Score end-to-end error at a fixed cycle budget, and pin the scorer",
     "<p>Fitness is the error a method delivers within {budget} cycles, so a cheap "
     "method gets to take more, smaller steps. Cost is counted analytically from the "
     "tableau under two Cortex-M0+ multiplier models. A classical optimizer fills a "
     "MAP-Elites grid, and a language model in the outer loop chooses where to search "
     "but never touches the scorer. Ten files are hashed, and the container will not "
     "start if the hash changes.</p>",
     "architecture.html", "how the system is built"),
    ("result", "Floor rounding is a bias the search can use",
     "<p>On one test problem the true answer is smaller than one Q15 step, and the bias "
     "carries the cheapest method to the closest value the format has, while rk4, the "
     "textbook favorite, ends up several times further away. Searched against that bias, "
     "the best coefficients are not the textbook ones.</p>",
     "results.html", "six findings, with their caveats"),
    ("verify", "Every number traces to a file, and the demo checks itself",
     "<p>The charts are built from one analysis file recomputed from the run archive. "
     "The demo page re-implements the Q15 integrator in the browser and, on load, "
     "compares all {demo_cases} of its runs with the pinned Python evaluator down to the "
     "final int16 state. The build fails if any of them differ.</p>",
     "architecture.html#tests", "how it is tested"),
)

CLASSES_LEAD = """
<p class="lead">The run takes turns between three classes of integrator. Only the
explicit class is scored by the pinned verifier. The live findings site gives each class
its own page.</p>
"""

# (class, status label, one paragraph). The card links to the class page on rk-findings.
CLASSES = (
    ("explicit", "scored",
     "Fixed-step explicit tableaus, found by MAP-Elites and CMA-ES and scored by the "
     "pinned verifier in Q15 at a fixed cycle budget. Every result on the key findings "
     "page comes from this class."),
    ("implicit", "measured, not scored",
     "Two-stage SDIRK methods for stiff problems, enumerated over a dyadic grid with a "
     "fixed Newton iteration count. They are ranked by the cycles they need to reach a "
     "tolerance, in float64, and their order is not checked by the pinned verifier."),
    ("adaptive", "measured, not scored",
     "Embedded pairs on the dyadic lattice with a division-free step-size controller. "
     "They are ranked the same way as the implicit class: cycles to reach a tolerance, "
     "in float64, not order-verified."),
)

SOURCE_LEAD = """
<p class="lead">Four public repositories. Every number on this site traces back through
them to the code that produced it.</p>
"""

REPOS = (
    ("rk-harness", "https://github.com/jgoetzmann/rk-harness",
     "The package the container runs: verifier, cost model, evaluator, search, site "
     "generator, and the tests that gate all of it."),
    ("rk-work", "https://github.com/jgoetzmann/rk-work",
     "Run data: the append-only archive, the hypothesis ledger, and the validation and "
     "benchmark results, written by the container every cycle."),
    ("rk-findings", "https://github.com/jgoetzmann/rk-findings",
     "The numbers site, rebuilt by the container every cycle with no human in the "
     "loop."),
    ("rk-overview", "https://github.com/jgoetzmann/rk-overview",
     "This site, and the tools that build it from the run archive."),
)

# ------------------------------------------------------------------------ architecture

ARCH_SUB = "How the run is built, from the container boundary down to the arithmetic."

ARCH_LEAD = """
<p>The reasons behind each piece are on the
<a href="design-decisions.html">design decisions</a> page.</p>
"""

ARCH_REPOS = """
<p><code>rk-work</code> holds the run's data: the append-only archive of every verified
tableau and the hypothesis ledger. The event stream and run state are gitignored and stay
on the host. A fifth, private repository holds the scripts and configuration that run all
of this on one machine; it is not linked here.</p>
"""

ARCH_BOUNDARIES = """
<p>The design assumes the search would optimize the scorer instead of the score if it
could. Four boundaries rule that out.</p>
<ul>
<li>The scorer is read-only. <code>rk-harness</code> is mounted read-only, and the
container will not start if the verifier hash has changed
(<a href="#verify">verification</a>).</li>
<li>No credential reaches the agent. The GitHub token stays on the host, the container
gets a filtered environment, and the host watchdog does every push.</li>
<li>The model never grades itself. Tiers and hypothesis verdicts are computed by code
from the archive, and a directive with an unknown key is rejected.</li>
<li>Model-written code is quarantined. A problem the model writes runs only after an
AST-checked import allowlist, determinism and time bounds, a range check and a reference
solution. Even then it can join only the held-out set, so the optimizer never trains on
it.</li>
</ul>
"""

ARCH_CYCLE = """
<p>The runner executes one cycle at a time. Replay rebuilds all state from the
append-only archive, nothing before the fsynced append has side effects, and state files
are written atomically. Replay also drops a torn last line, so a crash costs at most one
cycle and repeating a cycle is safe.</p>
"""

ARCH_LANES = """
<p>Each cycle belongs to one method class, and the loop rotates among them. An explicit
cycle runs the diagram above. An adaptive or implicit cycle runs that class's lane
search instead: it enumerates candidates deterministically and measures how many cycles
each needs to reach a tolerance on the validation problems, in float64.</p>
<p>Lane cycles append to their own archives, <code>rk-work/adaptive_archive</code> and
<code>rk-work/implicit_archive</code>. The verifier hash does not pin them and no score
reads them, so the explicit archive stays the only scored record. Each lane keeps a
capped elites document ranked by cycles to tolerance, and that document is what the
findings class pages publish. A separate side-track executor measures fixed design
questions for the same two classes and records every point in
<code>rk-work/sidetrack/ledger.jsonl</code>.</p>
"""

ARCH_GATE = """
<p>Six modules decide every score and four fixture files pin their golden values.
<code>VERIFIER_HASH</code> is a sha256 over those ten files. The entrypoint recomputes it
at every start and every archive record stores it, so a change to any byte shows up
twice. The pre-flight drill changed one line of <code>coeffrep.py</code> and the
container refused to start with "VERIFIER HASH MISMATCH". With the line restored, it
started normally.</p>
<p>Once the runner is up, each candidate passes nine checks, all plain code. Only the
primary cost model's columns can reject a candidate; the slow and AVR columns are kept
for breadth.</p>
<details class="fold"><summary>The nine checks, cheapest first</summary><div>
<ol class="checks">
<li><code>NOT_EXPLICIT</code>: A must be strictly lower triangular.</li>
<li><code>ROW_SUM_INCONSISTENT</code>: c must equal the row sums of A.</li>
<li><code>DYADIC_IMPOSSIBLE</code>: no all-dyadic tableau reaches order 3, because the
order-3 condition sums to 1/3, which no dyadic rational equals.</li>
<li><code>ORDER_NOT_MET</code>: exact rational residuals over rooted trees, never
floats.</li>
<li><code>COEFF_UNREPRESENTABLE</code>: a range check only. An inexact coefficient such
as 1/3 is recorded, not rejected.</li>
<li><code>Q15_OVERFLOW</code>: the trajectory must keep a 2&times; amplitude margin.</li>
<li><code>UNSTABLE</code>: the stability interval must be usable.</li>
<li><code>NO_ASYMPTOTIC_WINDOW</code>: the measured-order fit found no consistent
slope.</li>
<li><code>NAN_OR_INF</code>: any non-finite value anywhere is fatal.</li>
</ol>
</div></details>
"""

ARCH_ARITH = """
<p>States are Q15: int16 at scale 2<sup>&minus;15</sup>. A multiply is
<code>(a*b) &gt;&gt; 15</code> with an arithmetic shift, which rounds toward negative
infinity, as ARM's ASRS does and C's truncation does not (q15_mul(&minus;1, 1) is
&minus;1 under floor and 0 under truncation); the vectors where the two disagree are
pinned as fixtures. Nothing saturates and nothing wraps. A value outside int16 raises and
becomes a verifier rejection, because the M0+ has no SSAT and saturating in software
would need a branch, which breaks exact cycle counts.</p>
<p>The harness keeps floor rounding because shipped code would floor too;
<a href="results.html#floor-flip">key finding 2</a> measures what it does to the
error.</p>
<p>Coefficients are not Q15. Each one is an integer and a shift, m/2<sup>s</sup>,
applied as <code>(v*m) &gt;&gt; s</code>, since rk4's 1 and kutta3's 2 do not fit in
[&minus;1, 1). When no exact pair exists (1/3, for instance) the closest one is used and
the gap is recorded as quantization error, a measured property rather than a
rejection.</p>
<p>A derivative can be larger than the state it drives, so such a problem stores it with
an extra power-of-two factor (DERIV_SCALE, {deriv_scale} on rc_thermal, 1 elsewhere)
that the step undoes exactly through the step-size constant.</p>
"""

ARCH_COSTMODEL = """
<p>Cycles are counted analytically, with no compiler, emulator or board in the loop, so
the count is a pure function of the tableau and the same on every machine. Three models
price five kinds of operation; the table is read from the pinned
<code>costmodel</code> module.</p>
{table}
<p>A coefficient of 0 or &plusmn;1 costs nothing extra. Any other costs the cheaper of a
shift-add expansion (w shifts and w &minus; 1 adds, w being the CSD weight of m) and one
hardware multiply plus a shift. With a 1-cycle multiplier the multiply nearly always
wins; with a 32-cycle one the shift-add usually does, so low-weight coefficients get
much cheaper. Derivative evaluation is left out, since it costs the same for every
method with the same stage count. A hand-counted ARMv6-M sequence pinned as a fixture
must match the model under both M0+ models, and the
<a href="results.html#anchor">anchor result</a> is pinned as golden test G21.</p>
"""

ARCH_CANDIDATES = """
<p>Phases 0 and 1 enumerate their spaces completely, so their results hold over the
whole enumerated space, and the findings site labels them that way; phase 0 is
<a href="results.html#phase0">key finding 5</a>. Phases 2 and 3 run CMA-ES islands over
the lower triangle of A, snapped to dyadic values, then solve b exactly over the
rationals from the order conditions, which are linear in b once A is fixed. Snapping b
as well would make order 3 and above impossible (the <code>DYADIC_IMPOSSIBLE</code>
check above). When the requested order has no exact solution for a snapped A, as often
happens at order 4, the projection falls back to the highest order it can solve and the
candidate is verified at that order.</p>
<p>CMA-ES minimizes search-set error plus a large penalty on order-condition residuals;
only the three search problems are visible to it.</p>
"""

ARCH_ARCHIVE = """
<p>Every verified candidate becomes one fsynced JSON line in a per-day file: the tableau
as exact fractions, its content hash, the full score vector, the tier, the verifier hash
in force, what motivated it, and a UTC timestamp. Replay drops a line that fails to
validate and rejects a record whose hash does not match its tableau.</p>
<p>The working structure is MAP-Elites: one grid per order, with cells keyed by stage
count and a log2 band of the m0plus_fast cycle count. A cell's elite is the record with
the lowest held-out error, and a tie keeps the earlier record. Replay also keeps running
statistics per order and stage count, which the hypothesis ledger's predicates read. A
problem admitted from quarantine runs in shadow for a fixed number of cycles before it
counts.</p>
"""

ARCH_OUTER = """
<p>The language model (Codex, authenticated on the host, mounted read-only) never touches
the inner loop. It emits JSON directives that can only narrow the search, such as target
order or stage counts. A schema rejects unknown keys and bounds every field, and a
malformed directive is discarded in favor of a deterministic fallback that searches the
emptiest grid cell. Calls stop at a plan-usage cap.</p>
<p>The model also proposes falsifiable hypotheses. Code assigns their ids and verdicts,
and each predicate must parse under a closed grammar with a hand-written parser. No eval
runs anywhere near model output, and a grep canary enforces that. A field such as
fast.p3s4.heldout resolves against the archive's cell statistics;
<a href="results.html#protocol">how the numbers were made</a> covers how a verdict is
assigned.</p>
<details class="fold"><summary>The predicate grammar, in full</summary><div>
<pre class="grammar">expr    := term (("AND" | "OR") term)*
term    := field op field | field op number
field   := model "." cell "." metric
model   := "fast" | "slow" | "avr_approx"
cell    := "p" digit "s" digit
metric  := "heldout" | "search" | "cycles" | "order"
op      := "&lt;" | "&gt;" | "&lt;=" | "&gt;=" | "=="</pre>
</div></details>
<p>A literature loop searches the web for one topic at a time and feeds each digest into
later prompts. The digests and the model's interpretations are published in the findings
site's research log (<a href="{live}hypotheses.html#literature">digests</a>,
<a href="{live}hypotheses.html#interpretation">interpretations</a>), labeled as
model-written, after a softener removes priority-claim words.</p>
"""

ARCH_HOST = """
<p>A PowerShell watchdog on the host kills the container on a stale heartbeat, stops it
on overspend or low disk, and pauses it on battery or foreground CPU load. A wrongful
kill heals itself, since the restart policy brings the container back through the start
gate. Operational settings live in a workspace <code>config.json</code>; scientific
thresholds live in the hash-pinned code, because changing one would invalidate the
archive. Storage is UTC everywhere, and only display code converts to US Central.</p>
"""

ARCH_TESTS = """
<p>The suite collects <strong>{tests:,} tests</strong> in {tiers} numbered tiers that
follow the dependency stack, from fixed-point arithmetic up to the findings pages. Golden
tests (G-numbered) pin behavior to fixture values written before the code existed, down
to exact measured orders and cycle counts. Canary tests (K-numbered) guard against
gaming: K1 plants a candidate tuned on the search set and asserts that it can earn
search_only but never heldout_verified, and K2 asserts that a winner on a single problem
family stays unreplicated. The {gate} golden and canary cases are also the container's
start gate.</p>
"""

ARCH_PREFLIGHT = """
<p><code>scripts/preflight.py</code> executes every item on the pre-flight checklist
that a machine can check, and writes the report. Its drills act rather than assert: A1
writes to <code>/harness</code> from a running container and expects "Read-only file
system", and D5 feeds the optimizer the held-out set, watches the search/held-out gap
collapse to zero, and watches it come back on revert.</p>
"""

ARCH_REPRO = """
<p>The same seed produces a byte-identical archive, and an acceptance test requires it:
the evaluator reads no clock and draws no random numbers, and derived state replays from
the archive files alone. The findings site is a pure function of the archive. This site
is not, because it also reads the test collection and the latest analysis at build
time.</p>
"""

# -------------------------------------------------------------------- design decisions

DECISIONS_SUB = "Every deliberate choice, and what the build did to it."

# Trusted HTML: generate.py places it without escaping.
DECISIONS_LEAD = (
    "The {n} decisions from "
    "<a href=\"https://github.com/jgoetzmann/rk-overview/blob/main/DESIGN.md\">DESIGN.md</a>, "
    "written before any code existed. Each gives the original context, then what the "
    "working system does now and what the choice cost; the tag says whether it survived "
    "the build ({n_rev} were revised).")

# (anchor slug, title, context before the build, what the build did). Slugs are
# deep-link anchors: stable, short, never reused. The two halves are trusted HTML.
DECISIONS = (
    ("quantization",
     "The problem is quantization, not coefficient prettiness",
     "In floating point, h&middot;b constant-folds and 1/3 costs the same as 0.25. The "
     "premise only survives in fixed point on an FPU-less MCU, where a power-of-two "
     "coefficient becomes a shift. Scope narrowed to that case.",
     "Kept, and measured (<a href=\"results.html#crossover\">key finding 3</a>)."),
    ("dyadic-theorem",
     "Order &ge; 3 admits no all-dyadic tableau",
     "Dyadic rationals are closed under addition and multiplication, and "
     "&Sigma; b&middot;c&sup2; = 1/3 is not dyadic. So the objective is to minimize "
     "non-dyadic multiplies subject to order, and the verifier code DYADIC_IMPOSSIBLE "
     "keeps the search out of the empty region.",
     "Kept, and it shaped the search space. A is snapped to dyadic values but b is solved "
     "exactly over the rationals, because snapping b would run into this very theorem. "
     "The verifier rejects all-dyadic order-3 claims without evaluating them (tests "
     "V5 to V7)."),
    ("static-counting",
     "Static cycle counting, not simulation, not hardware",
     "The inner loop is branchless straight-line code, so summing instruction costs "
     "gives an exact count and a real worst-case figure, and host load cannot disturb "
     "the metric.",
     "Kept, and sharpened: the count is analytic from the tableau, with no compiler or "
     "disassembly in the loop. One hand-counted ARMv6-M sequence, reproduced exactly by "
     "a test, ties the model to hardware, and emit_c exists for a one-off human "
     "cross-check."),
    ("targets",
     "Cortex-M0+ primary, AVR advisory, two M0+ multiplier variants",
     "The M0+ has no FPU, divide or long multiply, so fixed point is forced. Running a "
     "1-cycle and a 32-cycle multiplier model costs nothing and shows whether hardware "
     "awareness changes the ranking.",
     "Kept, and the ranking does change: rk4 is cheaper with the fast multiplier and rk38 "
     "with the slow one (the <a href=\"results.html#anchor\">anchor result</a>). After a "
     "live candidate was rejected on an infinity in the AVR column, verification was "
     "restricted to the primary-model columns."),
    ("q15-overflow",
     "Q15, wrapping semantics, overflow as a rejection",
     "Q31 would have to be synthesized on the M0+, and saturation needs a compare and "
     "branch that breaks exact counting. Overflow at 2&times; amplitude is a verifier "
     "rejection, which makes it a property of the method rather than a runtime cost.",
     "Revised on one point: nothing wraps. A value outside int16 raises Q15OverflowError "
     "and becomes a verifier rejection. One addition the spec missed: rc_thermal's "
     "derivative times its state scale leaves Q15 range, so derivatives carry a "
     "per-problem power-of-two scale (DERIV_SCALE, {deriv_scale} there) that the step "
     "undoes through h. Floor rounding turned out to be an experimental variable in its "
     "own right (<a href=\"results.html#floor-flip\">key finding 2</a>)."),
    ("inner-outer",
     "Classical optimizer in the inner loop, LLM in the outer loop",
     "A six-parameter space has gradients, so CMA-ES does better than an LLM mutation "
     "operator at no cost. The LLM decides what to search and interprets what came "
     "back.",
     "Kept. When order-4 islands produced nothing (an exact order-4 b is rarely "
     "solvable over a dyadic A), the fix was a projection fallback in the optimizer, not "
     "more LLM. The outer loop grew hypotheses and a literature loop."),
    ("heldout-split",
     "Search/held-out split, enforced structurally",
     "The optimizer has no code path that reads HELDOUT_SET, and the held-out gap is a "
     "dashboard metric so it cannot rot unnoticed.",
     "Kept literally: a test walks the optimizer's import graph to enforce it, and the "
     "D5 drill shows the gap collapsing when the optimizer is fed the held-out set "
     "(<a href=\"architecture.html#tests\">testing</a>). The gap is also a caveat on the "
     "best numbers (<a href=\"results.html#efficiency\">key finding 1</a>)."),
    ("map-elites",
     "MAP-Elites, one grid per order",
     "Descriptors are stage count and cycle-cost bucket, which gives a table of results "
     "rather than a single champion.",
     "Kept unchanged. The findings site's explicit page and cell pages are built from "
     "these grids, and a cell's incumbent is what tier assignment compares against."),
    ("equal-budget",
     "Equal cycle budget, never equal step size",
     "A 2-stage method gets twice the steps of a 4-stage method for the same cost, and "
     "equal-h comparisons are the most common route to a wrong conclusion.",
     "Kept, and it frames every result on the "
     "<a href=\"results.html\">key findings page</a>: the rank flips and the efficiency "
     "frontier only exist at equal budget."),
    ("resource-limits",
     "Fixed resource limits plus a pause watchdog",
     "Low cpu-shares and docker pause on contention keep the run out of the way in about "
     "forty lines, with no dynamic allocation and no GPU.",
     "Kept, and grown a little; the <a href=\"architecture.html#host\">host layer</a> "
     "lists what the watchdog does now. Thresholds live in config.json rather than in "
     "code."),
    ("credentials",
     "Credentials outside the container, harness mounted read-only",
     "If the agent can write the verifier, the shortest path to a high score is editing "
     "the scorer. The token was to be scoped to rk-work and rk-findings, with the 403 on "
     "rk-harness as an acceptance test.",
     "Half kept. The read-only mount and pinned hash stand, but the token scoping did not "
     "survive: the owner's token could write everywhere, and the 403 probe passed for the "
     "wrong reason. The credential now never enters the container; a filtered env "
     "file and host-side pushes make that independent of token scope."),
    ("numbers-not-claims",
     "Auto-publish numbers, never claims",
     "The site emits values with mechanically assigned tiers, so a wrong result is a "
     "wrong number in a table, not a claim that needs retracting.",
     "Amended by the owner, with the guard intact. The findings site also publishes "
     "model-written interpretations and literature digests, labeled as such and passed "
     "through a softener that replaces priority-claim words. The banned-words guard still "
     "fails any page it rejects, and it blocked real builds until the softener "
     "existed."),
    ("encourager",
     "The encourager may change direction but not stop",
     "Before a calendar date it can only redirect, widen, hypothesize or advance phase. "
     "A set-and-forget system with no calendar runs until the operator gets bored.",
     "Kept. PACKAGE (re-verify everything, no new directions) opens {package_date} and "
     "FREEZE {freeze_date}, property-tested over random states and exercised through the "
     "real clock path."),
    ("falsification-first",
     "Falsification experiment first",
     "If derivative evaluation swamps coefficient arithmetic, the thesis is dead, so find "
     "out in week one rather than month three.",
     "Kept, and the verdict was stored as it came out, \"{fals_verdict}\" "
     "(<a href=\"results.html#crossover\">key finding 3</a> has the numbers)."),
)

CUTS = """
<p>Adaptive step size and Newton-iteration implicit methods break the execution-time
certificate that hard real-time needs, so they are wrong for the target whatever they
cost. Order above 4 and linear multistep methods multiply the search space with no
reason to expect a larger quantization effect. Rosenbrock methods remain the natural
second project. The build added one item: round-to-nearest is measured as a
counterfactual on the key findings page (<a href="results.html#floor-flip">finding
2</a>) rather than searched over, because changing the arithmetic changes every score in
the archive.</p>
<p>Two of those cuts have since been revisited, on terms that narrow the real-time
objection. The adaptive class uses a division-free controller and books each attempt at
its worst-case cycles, though the number of attempts still depends on the data. The
implicit class fixes its Newton iteration count so each step costs the same. Both are
measured outside the scored archive, on the findings site's
<a href="{live}adaptive.html">adaptive</a> and <a href="{live}implicit.html">implicit</a>
pages.</p>
"""

PRIOR_ART = """
<p>RKTK (Zhang, 2019) already runs unstructured numerical searches over Butcher order
conditions and holds a stage-count record at order 10, so numerical tableau search is not
the contribution. That line of work optimizes order, stage count and error constants in
exact arithmetic. It does not price coefficients against a hardware cost model or measure
end-to-end error in fixed point, and that gap is narrow enough to finish. The run's
literature loop keeps collecting adjacent work (fixed-point ODE solvers, constant
multiplication, rounding-error analysis), and its digests are in the findings site's
<a href="{live}hypotheses.html#literature">research log</a>.</p>
"""

# ------------------------------------------------------------------------ key findings

RESULTS_SUB = "What the explicit search found, at snapshot {date}."

HEADLINE_VERDICT = """
<p class="verdict">At a fixed budget of {budget} cycles on a Cortex-M0+ cost model, the
search found Runge-Kutta methods with up to <strong>{best_x}&times;</strong> lower
held-out error than the best classical method. The data also shows why: Q15's floor
rounding adds a bias of about half an LSB to every multiply, and that alone reorders the
classical methods before any search starts. The <a href="demo.html">demo</a> lets you
watch it happen.</p>
"""

RESULTS_SCOPE = (
    "Unless a figure says otherwise: a {budget}-cycle budget per problem, the m0plus_fast "
    "cost model, Q15 with floor rounding, the four held-out problems. Charts come from "
    "tools/key_findings.json; finding 6 reads rk-work/validation/results.json.")

ANCHOR_TITLE = "The anchor result"

ANCHOR_TEXT = """
<p>rk4 and rk38 are both four-stage, order-4 methods with the same stability polynomial,
and textbooks treat them as interchangeable. Priced against a real multiplier they are
not. With a 1-cycle multiplier rk4 is cheaper ({rk4_fast} against {rk38_fast} cycles per
step). With a 32-cycle multiplier rk38 is cheaper ({rk38_slow} against {rk4_slow}),
because rk4's coefficients need more shift-add work. Which one to ship depends on the
multiplier the chip has.</p>
"""

F_EFFICIENCY_INTRO = """
<p>The archive keeps one elite per MAP-Elites cell (order, stage count, cycle-cost
bucket). {cells_total} cells are occupied: {cells_disc} by discovered methods and
{cells_class} by classical ones ({class_cells}). Each discovered cell is compared with
every classical method of equal or lower per-step cost, since a cheaper method could
always be swapped in. {won_sentence} The median error ratio, discovered over classical,
is {median_ratio}, and the best is {best_ratio}.</p>
"""

F_EFFICIENCY_WON_ALL = "All {cells_disc} discovered cells have the lower held-out error."
F_EFFICIENCY_WON_SOME = ("{cells_won} of the {cells_disc} discovered cells have the lower "
                         "held-out error.")

# Finding 1's heading, chosen the same way as the sentence above.
F_EFFICIENCY_TITLE_ALL = "Discovered methods lead in all {cells_disc} cells"
F_EFFICIENCY_TITLE_SOME = "Discovered methods lead in {cells_won} of {cells_disc} cells"

F_EFFICIENCY_INTERP = """
<p>The best discovered method is a {bd_stages}-stage, order-{bd_order} tableau at
{bd_cycles} cycles per step, with held-out error {bd_err} against {anchor_err} for
{anchor_name}, the best classical method. Every coefficient is dyadic, so the method
needs only shifts and adds.</p>
<details class="fold"><summary>Its tableau and its error on each held-out
problem</summary><div>
<p>A = {bd_A}, b = {bd_b}, c = {bd_c}. Measured order {bd_measured}. Held-out error per
problem: {bd_per_problem}.</p>
</div></details>
<p>Two caveats. Elites are chosen by held-out error from {archive_n} archived candidates,
so the best values carry selection bias, although the optimizer itself only sees
search-set error. And a tier is a mechanical comparison with the cell's incumbent when
the record is written, not a validation grade: the best cell is {bd_tier}, and
{cells_hv} of the {cells_disc} discovered elites are heldout_verified.</p>
"""

F_FLIP_INTRO = """
<p>Every Q15 multiply rounds toward negative infinity, as ARM's <code>ASRS</code> does,
so the error from each product leans the same way. At these budgets that bias piles up
faster than truncation error shrinks. The counterfactual reruns the same {n_methods}
methods, budget and problems with round-to-nearest.</p>
"""

F_FLIP_INTERP = """
<p>On the three search problems, floor puts euler first (RMS {fl_euler}) and rk4 last
({fl_rk4}, {fl_ratio}&times; worse). Round-to-nearest restores the textbook order, with
rk4 ahead of euler ({rd_rk4} against {rd_euler}). Per problem, the best method changes on
{n_changed} of the {n_problems} problems.</p>
<p>Dahlquist shows the mechanism most clearly. Under floor, {dq_tie} all report error
{dq_err}, which is the entire reference value: the Q15 state decays to exactly zero, the
true answer is below one LSB, and floor's downward bias lands on it. Under
round-to-nearest the state stalls above zero and the error is up to {dq_worst}&times;
larger.</p>
"""

F_CROSSOVER_INTRO = """
<p>The premise was tested before the search started. If truncation error dominated
roundoff at practical step sizes, classical analysis would already give the right answer
and the search would be pointless. The falsification run swept the step size on
{problem}, computing each method's error twice, in Q15 and in float64 over exactly the
same steps, so the gap between the curves is the arithmetic alone.</p>
"""

F_CROSSOVER_INTERP = """
<p>rk4's Q15 error bottoms out at {rk4_min}, separates from the float curve at h =
{rk4_cross}, and climbs back to {rk4_small} by h = {h_small}: below the crossover, more
steps mean more floored multiplies and less accuracy. heun2 separates at h =
{heun2_cross}. Both crossovers fall inside the practical step-size range, as the premise
needed.</p>
<p>The stored verdict is "{verdict}": coefficient arithmetic is {fast_lo} to {fast_hi}% of
per-step cycles under the fast multiplier, above the {proceed}% proceed line, but heun2
under the slow one sits at {heun2_slow}%, just under the {kill}% kill line. At the shared
budget under floor, rk4 is the best of the {n_flip} methods on {rk4_wins} of the
{n_problems} problems.</p>
"""

F_RC_INTRO = """
<p>rc_thermal is the archive's stiff problem: a three-state RC network decaying toward
equilibrium, with its derivative stored at DERIV_SCALE = {deriv_scale} and one LSB worth
{lsb} in physical units. All {n_classical} classical methods report errors between
{fe_min} and {fe_max}, a spread of {spread}%. They agree because every one of them
collapses.</p>
"""

F_RC_INTERP = """
<p>Each method drives the Q15 state to within {lsb_lo} to {lsb_hi} LSBs of the origin
(euler ends at raw state {euler_state}, rk4 at {rk4_state}) while the true solution
still has norm {ref_norm} at t = {t_end}, so the reported error is the reference itself.
Late in the decay the scaled derivative terms are a few LSBs, and floor turns them into
extra decay.</p>
<p>It is a floor effect, not a limit of Q15: under round-to-nearest rk38 reaches
{rk38_rd}, and the best discovered method on this problem, a {bdrc_stages}-stage,
order-{bdrc_order} tableau at {bdrc_cycles} cycles per step, reaches {bd_rc} while still
using floor.</p>
"""

F_PHASE0_INTRO = """
<p>Phase 0 is the one part of the space small enough to close completely: two-stage
methods with a21 on a dyadic lattice, {lattice} candidates, of which {valid} have
exactly representable b weights. All {valid} were enumerated, verified and archived, so
the result holds over the whole space rather than a sample.</p>
"""

F_PHASE0_INTERP = """
<p>The optimum is a21 = {opt_a21} with b = {opt_b}: held-out error {opt_err} at
{opt_cyc} cycles per step. The runner-up, a21 = {ru_a21}, is at {ru_err}, {gap}% away,
so call it a tie. Neither is a textbook method, and both have lower held-out error than
all {n_anchors} classical methods (the best of those is {anchor_name} at {anchor_err}).
Within the family, midpoint ranks {mid_rank} and heun2 {heun_rank} of {valid}.</p>
"""

F_VALIDATION_INTRO = """
<p>Everything above uses the archive's own search and held-out problems. The validation
suite asks whether the winners transfer to {n_prac} equations from embedded applications
({domains}) that no optimizer saw, run at the same {budget}-cycle budget in Q15 with
floor rounding and scored against independent reference solutions.</p>
"""

F_VALIDATION_INTERP = """
<p>The discovered methods have the lower error on {won} of the {n_prac} problems, with a
median error ratio (best discovered over best classical) of {median}. The widest margin
is on {wide} ({wide_d} against {wide_c} for {wide_cname}, {wide_x}&times;). The
three-stage champion from finding 1, coefficients unchanged, wins {champ_wins} of
them.{loss_sentence}</p>
<p>Float64 runs of the same tableaus and step counts are at least {float_x}&times; more
accurate in every case, so these errors measure quantization, and the largest raw Q15
value in any run is {max_q:,} of 32,767, so none leaned on overflow luck. The {n_stiff}
stiff problems tell a different story (overflow, not accuracy); they and the full tables
are on the <a href="{live}validation.html">findings validation page</a>.</p>
"""

F_VALIDATION_LOSS = (" On {p}, {c_name} reaches {c_err} against {d_err} for the best "
                     "discovered method (ratio {ratio}), so the transfer is strong but "
                     "not universal.")

# (slug, heading, intro, interpretation). Charts are attached by slug in generate.py.
FINDINGS = (
    ("efficiency", "{eff_title}",
     F_EFFICIENCY_INTRO, F_EFFICIENCY_INTERP),
    ("floor-flip", "Floor rounding reorders the classical methods",
     F_FLIP_INTRO, F_FLIP_INTERP),
    ("crossover", "Where quantization overtakes truncation",
     F_CROSSOVER_INTRO, F_CROSSOVER_INTERP),
    ("rc-thermal", "The rc_thermal quantization floor",
     F_RC_INTRO, F_RC_INTERP),
    ("phase0", "Phase 0, closed by enumeration",
     F_PHASE0_INTRO, F_PHASE0_INTERP),
    ("validation", "Practical problems nobody tuned for",
     F_VALIDATION_INTRO, F_VALIDATION_INTERP),
)

MATRIX_TITLE = "Discovered, classical and library methods"

MATRIX_LEAD = """
<p>The chart shows one column of the full matrix folded below it; no single column ranks
the methods.</p>
"""

MATRIX_FOOTNOTES = """
<h3>Where each column comes from</h3>
<ol class="checks foot">
<li><strong>a.</strong> Held-out RMS error at the {budget}-cycle budget, m0plus_fast, Q15
with floor rounding, from <code>tools/key_findings.json</code> (series
<code>frontier_cycles_vs_heldout</code>, matched by tableau hash). The libraries never
ran this protocol, because they are adaptive and float64.</li>
<li><strong>b.</strong> Problems where this method has the lowest Q15 error of the
{n_val_methods} tested, from <code>rk-work/validation/results.json</code>, split into
practical ({n_prac} non-stiff) and stiff ({n_stiff}). The libraries are not part of the
validation suite.</li>
<li><strong>c.</strong> Analytic cycles per step for one state and total CSD weight,
recomputed from each tableau with the pinned <code>costmodel</code> and
<code>coeffrep</code> modules. CSD weight is the shift-add length of the coefficient
multiplies, a proxy for code size. Adaptive libraries have no fixed cycles per step.</li>
<li><strong>d.</strong> Python wall clock per step: the median across the scored
problems of per-problem medians ({repeats} repeats after {warmup} warmups, gc paused),
from <code>rk-work/benchmark/results.json</code>. Q15 rows run the pinned solver in the
interpreter and library rows run compiled code, so times compare like with like only
within a regime. Methods outside the benchmark run have no time.</li>
<li><strong>e.</strong> Behavior on the {n_stiff} stiff validation problems (stiffness
ratios {sr_lo} to {sr_hi}), from <code>rk-work/validation/results.json</code>. An
overflow is a <code>Q15OverflowError</code> from the pinned solver. The libraries were
not run on these problems.</li>
</ol>
"""

# Row notes for the matrix, keyed by row. Words only: the numbers are in the columns.
MATRIX_NOTES = {
    "euler": "Cheapest step and smallest code. Its tiny budget-driven steps stay inside "
             "the stability region on the stiff runs; the least accurate method "
             "elsewhere.",
    "midpoint": "The best classical method at this budget and arithmetic, and the "
                "strongest on the stiff problems.",
    "heun2": "Same cost class as midpoint and slightly worse throughout.",
    "rk4": "The textbook default. Its classically optimal coefficients buy nothing at "
           "this budget in Q15, and it is expensive under a slow multiplier.",
    "rk38": "Same order and stages as rk4, and cheaper under a slow multiplier.",
    "champion": "The three-stage, order-2 discovered champion, with the lowest held-out "
                "error in the archive. Its edge comes from how it handles floor bias, "
                "not from truncation order.",
    "elite3": "The best order-3 archive elite. Strong on the held-out set, but six "
              "stages mean large steps at a fixed budget, which the stiff problems "
              "punish.",
    "elite4": "The best order-4 archive elite, with the same six-stage stiff "
              "weakness.",
    "RK45": "SciPy's general-purpose default: explicit, adaptive, float64. It picks its "
            "step count at run time, so there is no fixed cycle cost to certify.",
    "Radau": "Implicit Radau IIA, built for the stiff problems that limit the explicit "
             "methods.",
    "BDF": "Implicit multistep for stiff problems, with adaptive step counts and no "
           "cycle model.",
    "LSODA": "Switches between stiff and non-stiff modes on its own; the same caveats as "
             "the other library rows.",
}

MATRIX_VERDICT = """
<p class="verdict">At matched tolerance the float64 libraries are far more accurate
than any Q15 method (median error ratio, best Q15 over best library, {lib_ratio}), and
at identical step counts float64 rk4 has the lower error in {rk4_cells} comparable
cells. That is the price of 16-bit floor arithmetic. The Q15 methods offer bounded
integer arithmetic at a fixed cycle cost known in advance, which no library here
provides, and within that regime the discovered methods have the lowest held-out error
(<a href="#efficiency">finding 1</a>). The stiff column is the weak spot of the whole
explicit class: an expensive tableau takes large steps at a fixed budget, leaves the
stability region and overflows. That failure is the argument for the implicit class.</p>
"""

SPEED_TITLE = "Measured speed"

SPEED_INTRO = """
<p>The benchmark checks the cycle model against a clock: it runs the champion and rk4
through the same pinned Q15 solver on all {sp_n} scored problems, so only the tableau
differs and the per-step time ratio isolates what the coefficients cost.</p>
"""

SPEED_INTERP = """
<p>Every problem lands within {maxdev}% of the predicted ratio. At the same budget the
champion also has the lower error on {sp_won} of the {sp_n} problems (rk4 keeps
{rk4_keeps}; median error ratio {sp_med}), so the time saved per step does not cost
accuracy. Python timings check the model rather than stand in for the chip; the protocol
and its caveats are on the <a href="{live}validation.html#speed">findings validation
page</a>.</p>
"""

PROTOCOL_TITLE = "How the numbers were made"

PROTOCOL = """
<p>Code assigns each record's tier when it is written (heldout_verified, search_only or
unreplicated) by comparison with its cell's incumbent. The model proposes hypotheses only
as predicates in a closed grammar, and code writes the verdict: no data or an effect
below Cohen's d of 0.2 is inconclusive, and refuted hypotheses are fed back into later
prompts. The premise got the same treatment, a falsification run with thresholds fixed in
advance and its verdict published either way (<a href="#crossover">finding 3</a>).</p>
"""

LIMITS_TITLE = "Limits"

LIMITS = """
<p>The cycle model is analytic and has never been checked against a physical chip inside
the loop. Measured order comes from one scalar problem in float64. Error is judged at the
final time, not along the trajectory, and floor is one hardware rounding convention among
several. Optimality claims from the enumerated phases hold only within their lattices,
and four held-out problems are a strong filter but not a statistical guarantee. The full
list, with the reasoning, is on the
<a href="{live}methodology.html">findings methodology page</a>.</p>
"""

OTHERS_TITLE = "The other two classes"

OTHERS = """
<p>Everything on this page is the explicit class. The implicit and adaptive classes are
measured in float64, outside the scored archive, and their results are on the findings
site's <a href="{live}implicit.html">implicit</a> and
<a href="{live}adaptive.html">adaptive</a> pages.</p>
"""
