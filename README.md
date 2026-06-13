# adversarial-testing

A self-improving **mutation-testing loop**: an LLM writes `pytest` tests that try to
*kill* deliberately-buggy variants ("mutants") of a reference implementation. The loop
keeps generating tests against the mutants still alive, escalating from a cheap model to
a strong one when progress stalls, and stops when every mutant is killed or a budget cap
is hit.

The signal that drives the loop is **ground truth, not opinion**: a mutant is "killed"
only when the generated test *passes* on the correct reference and *fails* on the mutant.
The Python interpreter decides — no LLM judges the result.

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

## Roadmap

- **TS/vitest adapter** (separate PR): a runner that mutates TypeScript source and verifies
  with `vitest`, so the same loop can target a real repo (e.g. NVIDIA/NemoClaw) instead of
  the Python toy. Scoped but not yet implemented.
