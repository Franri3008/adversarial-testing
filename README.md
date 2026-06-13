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
| `fixtures/` | reference implementation + its mutants (toy: `merge_intervals` + 5 bugs) |
| `generator.py` | asks the LLM for one test targeting the *surviving* mutants |
| `runner.py` | runs the test against reference (must pass) and each mutant (must fail) → kills |
| `harness.py` | kill-rate metric, plateau detector, JSONL logger, baseline |
| `main.py` | the loop: bulk tier → plateau → escalate to strategy tier → budget-cap stop |
| `llm.py` | two-tier model router (cheap "bulk" vs smart "strategy") with pluggable backend |

## Requirements

- Python 3.9+ and `pytest`
- A model backend — pick one:
  - **CLI (default, zero-config):** the [`claude`](https://docs.claude.com/claude-code) CLI,
    logged in. Uses your local Claude auth — no API key, no SDK install.
  - **SDK:** `pip install anthropic openai python-dotenv` and set `ANTHROPIC_APIKEY`
    (strategy tier) and/or `NEBIUS_APIKEY` (bulk tier).

## Run

```bash
pip install pytest          # plus `claude` CLI logged in (default backend)
python main.py
```

Example output:

```
baseline kill_rate=1.000 tokens=3038
iter  tier      cum_tokens   cost$    kill_rate  killed_this_round
   1  bulk            6290   0.150      1.000  ['M1_no_sort', 'M2_strict_overlap', 'M3_overwrite_end', 'M4_drop_last', 'M5_empty_returns_none']
all 5 mutants killed at iteration 1
final kill_rate=1.000 over 5 mutants, cost=$0.1501, log at run.jsonl
```

Per-iteration progress is also appended to `run.jsonl`.

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
