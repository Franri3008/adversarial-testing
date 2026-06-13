# adversarial-testing

A self-improving **mutation-testing loop**: an LLM writes `pytest` tests that try to
*kill* deliberately-buggy variants ("mutants") of a reference implementation. The loop
keeps generating tests against the mutants still alive, escalating from a cheap model to
a strong one when progress stalls, and stops when every mutant is killed or a budget cap
is hit.

The signal that drives the loop is **ground truth, not opinion**: a mutant is "killed"
only when the generated test *passes* on the correct reference and *fails* on the mutant.
The Python interpreter decides — no LLM judges the result.

> **Two loops live in this repo.** The **mutation loop** above (`main.py`) hardens a test
> suite against planted mutants. A second **find-and-fix loop** (`repair_main.py`) reuses
> the same runner/LLM contracts to *repair real bugs* — find a defect, write a failing
> test, fix the code, then mutation-test the new test to prove it bites. See
> [Find-and-fix mode](#find-and-fix-mode-repair_mainpy). To run both as one pipeline
> (repair → harden) on a single target, use [`orchestrate.py`](#orchestrated-run-orchestratepy).

## How it works

```
queue mutants ─▶ generate test (LLM) ─▶ run vs reference + mutants ─▶ score kill_rate
                      ▲                                                     │
                      └────────── plateau? escalate cheap▶smart ◀──────────┘
                                       stop on full-kill or budget cap
```

| File | Role |
|------|------|
| `fixtures/toy.py` | **current target** — reference `merge_intervals` + 5 mutants (M1–M5) |
| `generator.py` | asks the LLM for one test targeting the *surviving* mutants |
| `runner.py` | runs the test against reference (must pass) and each mutant (must fail) → kills |
| `harness.py` | kill-rate metric, plateau detector, JSONL logger, baseline |
| `main.py` | the loop: bulk tier → plateau → escalate to strategy tier → budget-cap stop |
| `llm.py` | two-tier model router (cheap "bulk" vs smart "strategy") with pluggable backend |

The active target is the toy fixture in `fixtures/toy.py`: a correct `merge_intervals`
plus five mutants — `M1_no_sort`, `M2_strict_overlap`, `M3_overwrite_end`,
`M4_drop_last`, `M5_empty_returns_none`.

## Requirements

- Python 3.9+ and `pytest`
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
LOOPIFY_MAX_ITERATIONS=1 python main.py
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

## Configuration

All optional, via environment variables:

| Variable | Default | Meaning |
|----------|---------|---------|
| `LOOPIFY_BACKEND` | `cli` | `cli` (uses `claude -p`) or `sdk` (Anthropic/Nebius SDKs) |
| `LOOPIFY_BULK_MODEL` | `haiku` | cheap tier — model alias for the CLI backend |
| `LOOPIFY_STRATEGY_MODEL` | `opus` | smart tier used when the loop escalates |
| `LOOPIFY_MAX_ITERATIONS` | `25` | hard cap on loop iterations |
| `LOOPIFY_COST_CAP` | `5.0` | stop once cumulative cost (USD) hits this (`0` disables) |
| `LOOPIFY_TOKEN_CAP` | `0` | stop once cumulative tokens hit this (`0` disables) |
| `ANTHROPIC_APIKEY` / `NEBIUS_APIKEY` | — | only for `LOOPIFY_BACKEND=sdk` |

## Stop conditions

The loop ends on the first of:
1. **Full kill** — every mutant killed (`kill_rate == 1.0`).
2. **Plateau on the strongest tier** — no kill-rate progress after escalating bulk → strategy.
3. **Budget cap** — `LOOPIFY_COST_CAP` or `LOOPIFY_TOKEN_CAP` reached.
4. **`LOOPIFY_MAX_ITERATIONS`** — hard backstop.

## Adding your own target

Drop a new fixture into `fixtures/` exposing `REFERENCE_SRC` (a string with one top-level
`def`) and `MUTANTS` (a list of `{"id", "description", "src"}`), then point `main.py` at it.
The runner derives the function name from the reference and injects it into each test as a
`pytest` fixture, so the same generated test runs unchanged against every variant.

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
python repair_plot.py        # optional: render repair_curve.png
```

Deterministic offline run (stub backend, no model calls):

```
$ LOOPIFY_BACKEND=sdk python repair_main.py
one-shot baseline: fixed 3/3 bugs, tokens 269
iteration  cumulative_tokens  bugs_fixed  kill_rate  fixed_this_round
        1               1716           1      0.333  B1_zero_total
        2               3209           2      0.667  B2_clamp_high
        3               4008           3      1.000  B3_clamp_low
no further bugs reported at iteration 4
loop fixed 3/3 planted bugs (graded), 3 tests in suite, log at repair_run.jsonl
```

Two metrics climb together: **bugs fixed** (repair progress) and **suite kill-rate** (test
quality). Progress is appended to `repair_run.jsonl`, with the one-shot baseline in
`repair_baseline.json`.

> **Note:** `repair_main.py` sets `PYTHONDONTWRITEBYTECODE` in-process to work around a
> stale-`.pyc` issue in the shared runner's reused temp dir (it rewrites `impl.py` per
> mutant, so `import impl` can load cached bytecode and report wrong kills on multi-mutant
> calls). The real fix belongs in `runner.py`; this avoids touching that frozen file.

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
$ LOOPIFY_BACKEND=sdk python orchestrate.py
=== PHASE 1: REPAIR (find & fix real bugs) ===
...
loop fixed 3/3 planted bugs (graded), 3 tests in suite
=== PHASE 2: HARDEN (mutation-test the repaired code to plateau) ===
harden          1               4336  bulk          1.000  0
=== ORCHESTRATION COMPLETE ===
repaired 3/3 planted bugs
final suite kill-rate 1.000 (3 tests, stop: full-kill)
total tokens 4336 (repair 4336 + harden 0)
```

`main.py` and `repair_main.py` stay usable standalone — the orchestrator just composes
them via the shared contracts (it imports `run_repair` and reuses `generate_test` /
`run_and_check`). Config: `ORCH_HARDEN_ITERS` (Phase 2 iteration cap, default 12) and
`ORCH_TOKEN_CAP` (total-token budget across both phases, `0` disables).

## Roadmap

- **TS/vitest adapter** (separate PR): a runner that mutates TypeScript source and verifies
  with `vitest`, so the same loop can target a real repo (e.g. NVIDIA/NemoClaw) instead of
  the Python toy. Scoped but not yet implemented.
