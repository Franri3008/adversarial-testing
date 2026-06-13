# adversarial-testing

A self-improving **mutation-testing loop**: an LLM writes tests (pytest or vitest) that try
to *kill* deliberately-buggy variants ("mutants") of a reference implementation. The loop
keeps generating tests against the mutants still alive, escalating from a cheap model to
a strong one when progress stalls, and stops when every mutant is killed or a budget cap
is hit.

The signal that drives the loop is **ground truth, not opinion**: a mutant is "killed"
only when the generated test *passes* on the correct reference and *fails* on the mutant.
The test runner (pytest or vitest) decides — no LLM judges the result.

> **Two loops live in this repo.** The **mutation loop** above (`main.py`) hardens a test
> suite against planted mutants. A second **find-and-fix loop** (`repair_main.py`) reuses
> the same runner/LLM contracts to *repair real bugs* — find a defect, write a failing
> test, fix the code, then mutation-test the new test to prove it bites. See
> [Find-and-fix mode](#find-and-fix-mode-repair_mainpy). To run both as one pipeline
> (repair → harden) on a single target, use [`orchestrate.py`](#orchestrated-run-orchestratepy).

## How it works

```mermaid
flowchart TD
    START(["Target: buggy code + oracle + planted bugs"])
    START --> P1

    subgraph P1["Phase 1 — Repair loop (repair_main.run_repair)"]
        direction TB
        F["find_bug(observation)<br/>strategy.py → has_bug, bug"]
        T["generate_bug_test<br/>repair_generator.py (strategy tier)"]
        X["generate_fix<br/>fixer.py"]
        V{"_verify_fix AND _suite_passes<br/>test bites · no regression"}
        H["_harden<br/>generate_test → run_and_check until mutants die"]
        F --> T --> X --> V
        V -->|"no · retry ≤ RETRY_PER_BUG"| T
        V -->|"yes"| H --> F
    end

    P1 -->|"repaired code + test suite"| P2

    subgraph P2["Phase 2 — Mutation loop (main.py)"]
        direction TB
        D["discover / load mutants"]
        G["generate test<br/>generator.py to llm.py · tier=bulk (haiku)"]
        E["verify · run_and_check<br/>pytest / vitest / repo-vitest"]
        S["score kill_rate · log · shrink survivors"]
        D --> G --> E --> S
        S -->|"survivors remain"| Q{"plateau?"}
        Q -->|"no"| G
        Q -->|"yes, escalate"| U["bulk to strategy (opus)"] --> G
    end

    P2 --> DONE(["kill_rate + bugs_fixed + cost · run.jsonl"])
```

Both loops share one **ground-truth contract**: a bug/mutant is only "caught" when a test
*passes on the correct code and fails on the broken code* — the test runner decides, not the
model. `main.py` runs the mutation loop alone, `repair_main.py` runs the repair loop alone, and
`orchestrate.py` runs Phase 1 → Phase 2 as a single repair-then-harden pipeline.

### As nested loops

The same system as nested loops (bounded `for … in range(...)` with early-exit stop
conditions). Every name below is greppable in the repo:

```
orchestrate.main()                                       # the run · orchestrate.py
│
├─ run_repair(buggy, oracle, planted_bugs)               # PHASE 1 · repair_main.py
│    for iteration in range(MAX_ITERATIONS):             #   per defect
│        decision = find_bug(observation)                #     strategy.find_bug → has_bug, bug
│        for attempt in range(RETRY_PER_BUG + 1):        #     retry a test+fix pair
│            generate_bug_test(code, bug)                #       repair_generator (strategy tier)
│            generate_fix(code, bug, test)               #       fixer
│            if _verify_fix(...) and _suite_passes(...): #       accept: bites + no regression → break
│        _discover_mutants(code)                         #     on accept (bulk tier)
│        _harden(code, accepted_tests, mutants):         #     strengthen the suite
│            for attempt in range(HARDEN_ATTEMPTS):      #
│                generate_test(code, surviving)          #         generator
│                _measure_kill_rate(...)                 #         → runner.run_and_check
│                    for m in mutants:                   #             per mutant
│                        _pytest_passes(test, m)         #               per run · GROUND TRUTH
│        # stop: (graded == total and kill_rate >= 1)  or  no_progress >= PATIENCE
│
└─ _phase2_harden(repaired_code, suite)                  # PHASE 2 · orchestrate.py
     for iteration in range(HARDEN_MAX):                 #   per round
         generate_test(code, surviving)                  #     bulk → escalate to strategy on plateau
         _measure_kill_rate(...) → run_and_check          #     per mutant → per run
```

| In the diagram | Real symbol · file |
|---|---|
| `find_bug` | `strategy.find_bug` |
| `generate_bug_test` | `repair_generator.generate_bug_test` |
| `generate_fix` | `fixer.generate_fix` |
| `_verify_fix` · `_suite_passes` · `_discover_mutants` · `_harden` · `_measure_kill_rate` · `run_repair` | `repair_main.py` |
| `generate_test` | `generator.generate_test` |
| `run_and_check` · `_pytest_passes` | `runner.py` |
| `_phase2_harden` · `main` | `orchestrate.py` |

Note: the **retry** loop (`RETRY_PER_BUG`) and the **harden** loop (`HARDEN_ATTEMPTS`) are
*siblings* inside the per-defect iteration, not a single deep chain; `main.py` standalone is
just the mutation loop (`generate_test → run_and_check`, escalate on plateau).

| File | Role |
|------|------|
| `fixtures/` | targets — each exposes `REFERENCE_SRC`, `MUTANTS`, and a `LANGUAGE` |
| `generator.py` | asks the LLM for one test (pytest or vitest) targeting the *surviving* mutants |
| `runner.py` | Python verifier — runs the test vs reference (must pass) + each mutant (must fail) → kills |
| `runner_ts.py` | TypeScript verifier — same contract, via a standalone `vitest` project (`ts_harness/`) |
| `runner_repo_ts.py` | TypeScript verifier that runs inside a real repo checkout, using the repo's own `vitest` config |
| `harness.py` | kill-rate metric, plateau detector, JSONL logger, baseline |
| `main.py` | the loop: bulk tier → plateau → escalate to strategy tier → budget-cap stop |
| `llm.py` | two-tier model router (cheap "bulk" vs smart "strategy") with pluggable backend |

### Targets

Pick a target with `FIXTURE` (default `toy`):

- **`toy`** (Python) — `merge_intervals` + 5 mutants. pytest verifier.
- **`duration_ts`** (TypeScript) — `parseDuration`, sourced from
  [NVIDIA/NemoClaw `src/lib/domain/duration.ts`](https://github.com/NVIDIA/NemoClaw/blob/main/src/lib/domain/duration.ts),
  + 5 mutants (incl. `M2_no_cap`, which drops the 30-minute "shields-down" security cap).
  vitest verifier.
- **`nemoclaw_duration_repo`** (TypeScript, repo-backed) — the same `parseDuration`, but read
  from a local NemoClaw checkout and tested through NemoClaw's **own** vitest config (see
  "Repo-backed mode" below).

## Requirements

- Python 3.9+ and `pytest`
- `matplotlib` — optional, only for rendering `repair_curve.png` (`pip install matplotlib`)
- A model backend — pick one:
  - **CLI (default, zero-config):** the [`claude`](https://docs.claude.com/claude-code) CLI,
    logged in. Uses your local Claude auth — no API key, no SDK install.
  - **SDK:** `pip install anthropic openai python-dotenv` and set `ANTHROPIC_APIKEY`
    (strategy tier) and/or `NEBIUS_APIKEY` (bulk tier).

## Run

```bash
pip install pytest          # plus the `claude` CLI logged in (default backend)
python main.py
```

Run a single iteration (handy for a quick check or demo):

```bash
MAX_ITERATIONS=1 python main.py
```

Real output from a 1-iteration run on `fixtures/toy.py`:

```
baseline kill_rate=1.000 tokens=3289
iter  tier      cum_tokens   cost$    kill_rate  killed_this_round
   1  bulk            4035   0.151      1.000  ['M1_no_sort', 'M2_strict_overlap', 'M3_overwrite_end', 'M4_drop_last', 'M5_empty_returns_none']
all 5 mutants killed at iteration 1
final kill_rate=1.000 over 5 mutants, cost=$0.1507, log at run.jsonl
```

On this toy the cheap `bulk` tier (haiku) writes one strong test that kills all five
mutants in the first iteration, so the loop stops on full-kill. Per-iteration progress is
also appended to `run.jsonl`:

```json
{"iteration": 1, "cumulative_tokens": 4035, "kill_rate": 1.0, "killed_this_round": ["M1_no_sort", "M2_strict_overlap", "M3_overwrite_end", "M4_drop_last", "M5_empty_returns_none"], "tier": "bulk", "cost_usd": 0.1507}
```

### TypeScript target (NemoClaw `parseDuration`)

One-time: install the standalone vitest harness (kept out of the loop's package graph):

```bash
cd ts_harness && npm install && cd ..
```

Then run the loop against the TS fixture (needs Node ≥18 + `claude` on PATH):

```bash
FIXTURE=duration_ts MAX_ITERATIONS=1 python main.py
```

Real output — the LLM writes a `vitest` test that kills all 5 mutants, including the
security cap removal:

```
baseline kill_rate=1.000 tokens=2129
iter  tier      cum_tokens   cost$    kill_rate  killed_this_round
   1  bulk            1956   0.141      1.000  ['M1_minute_multiplier', 'M2_no_cap', 'M3_default_unit_minutes', 'M4_allow_zero', 'M5_empty_returns_default']
all 5 mutants killed at iteration 1
final kill_rate=1.000 over 5 mutants, cost=$0.1407, log at run.jsonl
```

## Run against any repo (CLI)

Point the loop at a function in **any GitHub repo** — no fixture authoring. It fetches the
file, asks the strategy model to generate realistic mutants (each validated to compile),
infers the language from the extension, and runs the loop:

```bash
python3 main.py \
  repo=https://github.com/NVIDIA/NemoClaw \
  file=src/lib/domain/duration.ts \
  function=parseDuration \
  mutants=5
```

Real output — mutants are **auto-generated and compile-checked**, then killed:

```
[acquire] https://github.com/NVIDIA/NemoClaw :: src/lib/domain/duration.ts (typescript), target `parseDuration`
[acquire] 5 valid mutants: ['off_by_one_max', 'wrong_max_constant', 'zero_guard_allows_zero', 'wrong_default_unit', 'wrong_minute_multiplier']
baseline kill_rate=1.000 tokens=2509
iter  tier      cum_tokens   cost$    kill_rate  killed_this_round
   1  bulk            2817   0.035      1.000  ['off_by_one_max', 'wrong_max_constant', 'zero_guard_allows_zero', 'wrong_default_unit', 'wrong_minute_multiplier']
all 5 mutants killed at iteration 1
final kill_rate=1.000 over 5 mutants, cost=$0.0346, log at run.jsonl
```

| Arg | Meaning |
|-----|---------|
| `repo=` | a **local checkout path** (read from disk, no network), a repo URL (`https://github.com/owner/name`), or `owner/name` |
| `file=` | path to the source file (within the repo / checkout) |
| `function=` | the function under test |
| `mutants=` | how many mutants to generate (default 5) |

Already have the repo cloned? Point `repo=` at it to skip the fetch entirely:

```bash
python3 main.py repo=~/Codes/NemoClaw file=src/lib/domain/duration.ts function=parseDuration
```

Language is inferred from the file extension (`.ts`/`.tsx` → vitest, `.py` → pytest).
Requires the `gh` CLI authenticated; for TypeScript, install the harness once
(`cd ts_harness && npm install`). Env vars (iterations, caps, backend) apply as below.

**Limitations (today):** the target file must be **self-contained** (no unresolved
imports) so it loads in the standalone harness — `duration.ts` qualifies. Any mutant that
fails to compile is dropped, so a broken mutant never counts as a false kill.

## Repo-backed mode (real NemoClaw checkout)

The CLI above fetches a single file and tests it in an isolated harness. **Repo-backed
mode** is the highest-fidelity verifier: it runs the generated test through the *target
repo's own* `vitest` config, against the real source file swapped in place.

```bash
# one-time: a local NemoClaw checkout with deps installed
git clone https://github.com/NVIDIA/NemoClaw ~/Codes/NemoClaw
cd ~/Codes/NemoClaw && npm ci && cd -

FIXTURE=nemoclaw_duration_repo python main.py
```

How it works (`runner_repo_ts.py`): copy the checkout to a temp workspace (skipping
`.git`/`node_modules`, symlinking installed deps) → write the generated test beside the
target file → swap in the reference / each mutant at `src/lib/domain/duration.ts` → run
`npx vitest run --project cli <test>` so the repo's real config decides pass/fail. The
fixture (`fixtures/nemoclaw_duration_repo.py`) reads the live source and derives its 5
mutants by patching it, so it tracks whatever NemoClaw currently ships.

Config (env): `NEMOCLAW_REPO_PATH` (checkout location, default `~/Codes/NemoClaw`),
`NODE_BIN` (prepend a Node toolchain to PATH), `REPO_VITEST_TIMEOUT` (per-run seconds,
default 90).

## Configuration

All optional, via environment variables:

| Variable | Default | Meaning |
|----------|---------|---------|
| `FIXTURE` | `toy` | which target to run: `toy` (Python) or `duration_ts` (TypeScript) |
| `BACKEND` | `cli` | `cli` (uses `claude -p`), `sdk` (Anthropic/Nebius SDKs), or `stub` (deterministic offline, no network) |
| `BULK_MODEL` | `haiku` | cheap tier — model alias for the CLI backend |
| `STRATEGY_MODEL` | `opus` | smart tier used when the loop escalates |
| `MAX_ITERATIONS` | `25` | hard cap on loop iterations |
| `COST_CAP` | `5.0` | stop once cumulative cost (USD) hits this (`0` disables) |
| `TOKEN_CAP` | `0` | stop once cumulative tokens hit this (`0` disables) |
| `ANTHROPIC_APIKEY` / `NEBIUS_APIKEY` | — | only for `BACKEND=sdk` |

## Stop conditions

The loop ends on the first of:
1. **Full kill** — every mutant killed (`kill_rate == 1.0`).
2. **Plateau on the strongest tier** — no kill-rate progress after escalating bulk → strategy.
3. **Budget cap** — `COST_CAP` or `TOKEN_CAP` reached.
4. **`MAX_ITERATIONS`** — hard backstop.

A real backend (`cli`/`sdk`) that errors (auth, rate-limit, transport) now **fails loud** —
`llm.complete` raises rather than silently returning a stub, so a credential problem can't
masquerade as an (empty) plateau. Use `BACKEND=stub` for the explicit offline path.

> **Reproducibility & safety.** Runs are deterministic only under `BACKEND=stub`; the SDK
> path defaults to `temperature=0` but the `claude` CLI backend has no reliable seed and is
> non-deterministic by design. The runner **executes LLM-generated code on the host** — run
> it only against trusted targets. Container-level isolation is future work.

## Adding your own target

Drop a new module into `fixtures/` exposing `REFERENCE_SRC`, `MUTANTS` (a list of
`{"id", "description", "src"}`), and `LANGUAGE` (`"python"` or `"typescript"`; TS fixtures
also set `FUNCTION_NAME`). Select it with `FIXTURE=<module>`. The runner derives the
function under test from the reference and runs the same generated test against the
reference and every mutant — for Python via a pytest fixture, for TypeScript by swapping
`ts_harness/impl.ts`.

## Find-and-fix mode (`repair_main.py`)

Where the mutation loop assumes the code is correct and hardens the *tests*, find-and-fix
assumes the code is **buggy** and repairs it. Each iteration finds one real defect, writes
a test that captures the correct behavior (red on the buggy code, green once fixed),
patches the code, verifies the red→green transition, then **mutation-tests the new suite**
to prove the generated tests actually catch regressions.

```
observe code + bugs-already-fixed (memory)
  ─▶ find a bug (Claude)  ─▶ write a failing test (Nebius)  ─▶ fix the code (Claude)
       ─▶ verify red→green (runner)  ──reject──▶ record attempt, try next
              └──accept──▶ code = fixed, add test to suite
                   ─▶ mutate the fixed code, run suite vs mutants
                        ─▶ survivors? write more tests until they're killed
                   ─▶ log {bugs_fixed, kill_rate}  ─▶ repeat until no bug remains
```

| File | Role |
|------|------|
| `fixtures/buggy.py` | **target** — a single-function `grade` with 3 planted bugs + correct oracle |
| `strategy.py` | `find_bug(observation)` — Claude identifies one unfixed defect from the code + memory |
| `repair_generator.py` | `generate_bug_test` — Nebius writes a fixture-style test that exposes the bug |
| `fixer.py` | `generate_fix(code, bug, test)` — Claude patches the module |
| `repair_main.py` | the loop: find → test → fix → verify → harden → report |
| `repair_plot.py` | plots bugs-fixed + suite kill-rate vs cumulative tokens → `repair_curve.png` |

It reuses the **frozen contracts** unchanged: `generator.generate_test` (for the hardening
step) and `runner.run_and_check` / `llm.complete`. Fix verification is the same
`run_and_check` with roles inverted — the **fixed code as the reference** and the **buggy
original as the lone mutant** — so "mutant killed" means "the test fails on the old buggy
code" (a genuine red→green).

### Run

```bash
pip install pytest          # plus the `claude` CLI logged in (default backend)
python repair_main.py
pip install matplotlib       # only needed for the plot below
python repair_plot.py        # optional: render repair_curve.png
```

`repair_plot.py` renders a proper labeled, dual-axis chart when **matplotlib** is
installed (`pip install matplotlib`). Without it, the script falls back to a tiny built-in
PNG writer that draws the curves but no axis tick labels — install matplotlib for the
readable version.

#### Repair any repo (CLI)

Point the repair loop at a **buggy** function in any repo — no fixture, no answer key. It
loads the source (local checkout path or GitHub URL, same as the mutation loop), repairs it
iteratively, and reports fixes made + the suite kill-rate measured against mutants discovered
from the corrected code:

```bash
python repair_main.py repo=<url-or-path> file=path/to/file.py function=my_fn
```

Python targets only for now (the repair internals — `ast`-based test mangling, the pytest
runner — are Python-specific); a non-`.py` `file=` exits with a clear "Python only" message.
Without `repo=`/`file=` it runs the built-in planted `grade` fixture as before.

Deterministic offline run (stub backend, no model calls):

```
$ BACKEND=stub python repair_main.py
blind one-shot baseline: fixed 1/3 bugs in 226 tokens (produces no tests)
iter  cum_tokens  bugs_fixed   kill_rate  tests  note
   1        1673        1/3      0.333      1  fixed via B1_zero_total
   2        3424        1/3      0.333      1  no valid fix in 3 tries (1/3)
   3        4944        2/3      0.667      2  fixed via B2_clamp_high
   4        6787        2/3      0.667      2  no valid fix in 3 tries (1/3)
   5        7638        3/3      1.000      3  fixed via B3_clamp_low
all 3 planted bugs fixed and suite kills every regression at iter 5
LOOP    : fixed 3/3 planted bugs, 3 regression tests, 100% kill-rate, 7638 tokens
BASELINE: fixed 1/3 planted bugs, 0 regression tests, 226 tokens (blind one-shot)
log at repair_run.jsonl
```

This is the case for the loop: a single all-at-once "fix every defect" attempt patches
the obvious `ZeroDivisionError` crash but misses the two subtler boundary clamps — **1/3
bugs** for 226 tokens. The iterative loop's find → test → verify cycle closes all **3/3**,
trading more tokens for complete repair. In `repair_curve.png` the red ✕ (one-shot) sits
at 1 bug while the blue line climbs to 3.

Two metrics climb together: **bugs fixed** (repair progress) and **suite kill-rate** (test
quality). Progress is appended to `repair_run.jsonl`, with the one-shot baseline in
`repair_baseline.json`.

> **Note:** the shared runner rewrites `impl.py` per implementation in one reused temp dir,
> so `import impl` could load cached bytecode and report a wrong kill on multi-mutant calls.
> `runner.py` now runs each pytest subprocess with `PYTHONDONTWRITEBYTECODE=1`, so every
> implementation always loads fresh source — no caller-side workaround needed.

## Orchestrated run (`orchestrate.py`)

A thin orchestrator runs both loops as two **phases on one target** with a single token
budget and a combined report — repair the code, then harden the resulting suite to plateau:

```
Phase 1 · REPAIR  → run the find-and-fix loop until no bug remains (fixes code + seeds suite)
Phase 2 · HARDEN  → mutate the corrected code, keep generating tests (escalating bulk→strategy)
                    until full-kill, kill-rate plateau, or budget cap
→ "repaired N/total bugs, final suite kill-rate X%, total tokens T"
```

```bash
python orchestrate.py
```

Deterministic offline run (stub backend):

```
$ BACKEND=stub python orchestrate.py
=== PHASE 1: REPAIR (find & fix real bugs) ===
...
LOOP    : fixed 3/3 planted bugs, 3 regression tests, 100% kill-rate, 7638 tokens
=== PHASE 2: HARDEN (mutation-test the repaired code to plateau) ===
harden          1               7638  bulk          1.000  0
=== ORCHESTRATION COMPLETE ===
repaired 3/3 planted bugs
final suite kill-rate 1.000 (3 tests, stop: full-kill)
total tokens 7638 (repair 7638 + harden 0)
```

`main.py` and `repair_main.py` stay usable standalone — the orchestrator just composes
them via the shared contracts (it imports `run_repair` and reuses `generate_test` /
`run_and_check`). Config: `ORCH_HARDEN_ITERS` (Phase 2 iteration cap, default 12) and
`ORCH_TOKEN_CAP` (total-token budget across both phases, `0` disables).

## Running the tests

The harness has its own pytest suite under `tests/`. It runs fully offline (no network, no
model calls) by pinning the deterministic stub backend:

```bash
BACKEND=stub pytest -q
```

It covers the runner's kill detection (including a multi-mutant regression test for the
stale-`.pyc` bug), the kill-rate/plateau metrics, the repo/JSON/code parsers, the loud-failure
contract (a real backend with no credentials raises rather than stubbing), and the repair
loop's offline demo (3/3 planted bugs). TS/`npx`-dependent assertions skip when Node is absent.

## Roadmap

- **Auto-pick the target function** so `repo=` alone works (today you pass `file=`/`function=`).
- **Files with imports:** resolve sibling modules into the harness so non-self-contained
  functions can be targeted (today the target file must be self-contained).
- **More NemoClaw targets** across `src/lib/**` to grow coverage.
