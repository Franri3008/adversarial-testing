"""Benchmark suite for the adversarial-testing loop.

Runs each scenario in a subprocess under BACKEND=stub, reads the trailing
`run_finished` event from the loop's JSONL output, and diffs a whitelisted set
of metrics against `bench_baseline.json`. Any drift means harness, runner, or
prompt-shaping behavior changed — either fix it, or accept it with --update.

Stub backend is deterministic, so the diff is exact-match. This catches harness
regressions in CI for free; it does NOT measure LLM quality (use a real backend
benchmark over multiple seeds for that).

Usage:
  python bench.py              # run all, diff vs baseline, exit non-zero on drift
  python bench.py --update     # write current metrics as the new baseline
  python bench.py --only NAME  # run a single scenario by name
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.abspath(__file__))
BASELINE_PATH = os.path.join(ROOT, "bench_baseline.json")
LOG_DIR = os.path.join(ROOT, "bench_logs")

SCENARIOS: List[Dict[str, Any]] = [
    {
        "name": "harden_toy_stub",
        "kind": "harden",
        "cmd": [sys.executable, "main.py"],
        "env": {
            "BACKEND": "stub",
            "FIXTURE": "toy",
            "MAX_ITERATIONS": "3",
            "MUTANT_ROUNDS": "0",
        },
        "log_path": "run.jsonl",
    },
    {
        "name": "repair_buggy_stub",
        "kind": "repair",
        "cmd": [sys.executable, "repair_main.py"],
        "env": {"BACKEND": "stub"},
        "log_path": "repair_run.jsonl",
    },
]

METRIC_KEYS: Dict[str, tuple] = {
    "harden": (
        "kill_rate",
        "cumulative_tokens",
        "stop_reason",
        "total_mutants",
        "mutant_rounds",
        "killed_mutant_ids",
    ),
    "repair": (
        "kill_rate",
        "cumulative_tokens",
        "stop_reason",
        "bugs_fixed",
        "total_bugs",
        "suite_size",
        "fixes_made",
    ),
}


def _read_final_event(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    last = None
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("event") == "run_finished":
                last = obj
    return last


def _run_scenario(scenario: Dict[str, Any]) -> Dict[str, Any]:
    env = os.environ.copy()
    env.update(scenario["env"])
    proc = subprocess.run(
        scenario["cmd"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    log_src = os.path.join(ROOT, scenario["log_path"])
    os.makedirs(LOG_DIR, exist_ok=True)
    if os.path.exists(log_src):
        shutil.copy(log_src, os.path.join(LOG_DIR, scenario["name"] + ".jsonl"))

    final = _read_final_event(log_src)
    if final is None:
        return {
            "ok": False,
            "error": "no run_finished event in {}".format(scenario["log_path"]),
            "stdout_tail": (proc.stdout or "")[-400:],
            "stderr_tail": (proc.stderr or "")[-400:],
            "returncode": proc.returncode,
        }
    keys = METRIC_KEYS[scenario["kind"]]
    metrics = {k: final.get(k) for k in keys if k in final}
    return {"ok": True, "metrics": metrics, "returncode": proc.returncode}


def _load_baseline() -> Dict[str, Dict[str, Any]]:
    if not os.path.exists(BASELINE_PATH):
        return {}
    with open(BASELINE_PATH) as handle:
        return json.load(handle)


def _save_baseline(data: Dict[str, Dict[str, Any]]) -> None:
    with open(BASELINE_PATH, "w") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


USE_COLOR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return "\x1b[{}m{}\x1b[0m".format(code, text) if USE_COLOR else text


def _dim(s: str) -> str:   return _c("2", s)
def _red(s: str) -> str:   return _c("31", s)
def _green(s: str) -> str: return _c("32", s)


def _fmt(key: str, value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return "{:.3f}".format(value)
    if isinstance(value, int):
        return "{:,}".format(value)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "(none)"
    return str(value)


def _ordered_items(kind: str, metrics: Dict[str, Any]):
    """Yield (key, value) in the declared display order; unknown keys last."""
    order = METRIC_KEYS.get(kind, ())
    for key in order:
        if key in metrics:
            yield key, metrics[key]
    for key in metrics:
        if key not in order:
            yield key, metrics[key]


def _print_metrics_block(kind: str, metrics: Dict[str, Any]) -> None:
    items = list(_ordered_items(kind, metrics))
    label_width = max((len(k) for k, _ in items), default=0)
    for key, value in items:
        print("  {}  {}".format(_dim(key.ljust(label_width)), _fmt(key, value)))


def _diff_rows(kind: str, current: Dict[str, Any], baseline: Dict[str, Any]) -> List[tuple]:
    """Return [(key, old_fmt, new_fmt)] for changed fields, in display order."""
    rows = []
    seen = set()
    for key, _ in _ordered_items(kind, {**baseline, **current}):
        if key in seen:
            continue
        seen.add(key)
        b = baseline.get(key, "<missing>")
        c = current.get(key, "<missing>")
        if b != c:
            rows.append((key, _fmt(key, b), _fmt(key, c)))
    return rows


def _print_diff(name: str, kind: str, current: Dict[str, Any], baseline: Optional[Dict[str, Any]]) -> int:
    if baseline is None:
        print("{}  {}".format(name, _dim("(no baseline yet — run with --update)")))
        return 0
    rows = _diff_rows(kind, current, baseline)
    if not rows:
        return 0
    label_w = max(len(k) for k, _, _ in rows)
    old_w = max(len(o) for _, o, _ in rows)
    print(name)
    for key, old, new in rows:
        print("  {}  {}  {}  {}".format(
            _dim(key.ljust(label_w)),
            _red(old.ljust(old_w)),
            _dim("->"),
            _green(new),
        ))
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--update", action="store_true", help="overwrite baseline with current metrics")
    parser.add_argument("--only", help="run only the named scenario")
    args = parser.parse_args()

    scenarios = SCENARIOS
    if args.only:
        scenarios = [s for s in SCENARIOS if s["name"] == args.only]
        if not scenarios:
            names = ", ".join(s["name"] for s in SCENARIOS)
            print("no scenario named {!r}; choices: {}".format(args.only, names))
            return 2

    baseline = _load_baseline()
    results: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []

    kinds: Dict[str, str] = {s["name"]: s["kind"] for s in SCENARIOS}

    for scenario in scenarios:
        name = scenario["name"]
        print("\n" + _dim("running") + " " + name)
        result = _run_scenario(scenario)
        if not result["ok"]:
            errors.append("{}: {}".format(name, result["error"]))
            print("  " + _red("ERROR: " + result["error"]))
            if result.get("stderr_tail"):
                print("  " + _dim("stderr: " + result["stderr_tail"]))
            continue
        metrics = result["metrics"]
        results[name] = metrics
        _print_metrics_block(scenario["kind"], metrics)

    if args.update:
        merged = dict(baseline)
        merged.update(results)
        _save_baseline(merged)
        print("\nbaseline updated -> {}".format(os.path.relpath(BASELINE_PATH, ROOT)))
        return 1 if errors else 0

    print("\n" + _dim("--- diff vs baseline ---"))
    total_drifts = 0
    drift_scenarios = 0
    for name in results:
        n = _print_diff(name, kinds[name], results[name], baseline.get(name))
        if n:
            drift_scenarios += 1
            total_drifts += n
    if total_drifts:
        print("\n" + _red("REGRESSION") + ": {} metric(s) drifted across {} scenario(s).".format(
            total_drifts, drift_scenarios))
        print(_dim("Accept the change with: python bench.py --update"))
        return 1
    if errors:
        print("\n".join(errors))
        return 1
    print(_green("OK") + ": all {} scenario(s) match baseline.".format(len(results)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
