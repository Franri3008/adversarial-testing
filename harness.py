import json
from typing import Any, Callable, Dict, List

LOG_FIELDS = ["iteration", "cumulative_tokens", "kill_rate", "killed_this_round"]


def compute_kill_rate(killed_count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return killed_count / total


def make_log_entry(iteration: int, cumulative_tokens: int, kill_rate: float, killed_this_round: List[str]) -> Dict[str, Any]:
    return {
        "iteration": iteration,
        "cumulative_tokens": cumulative_tokens,
        "kill_rate": kill_rate,
        "killed_this_round": list(killed_this_round),
    }


def is_plateau(kill_rates: List[float], patience: int = 3, min_delta: float = 1e-9) -> bool:
    if len(kill_rates) < patience + 1:
        return False
    window = kill_rates[-(patience + 1):];
    return (max(window) - min(window)) <= min_delta


def run_baseline(reference_src: str, mutants: List[Dict[str, Any]], generate_fn: Callable, run_fn: Callable) -> Dict[str, Any]:
    gen = generate_fn(reference_src, mutants);
    tokens = gen["tokens"]["in"] + gen["tokens"]["out"];
    result = run_fn(gen["test_src"], reference_src, mutants);
    killed = result["killed_mutant_ids"] if result["reference_passed"] else [];
    kill_rate = compute_kill_rate(len(set(killed)), len(mutants));
    return make_log_entry(1, tokens, kill_rate, killed)


class JsonlLogger:
    def __init__(self, path: str):
        self.path = path;
        self.entries = [];
        open(self.path, "w").close();

    def append(self, entry: Dict[str, Any]) -> None:
        self.entries.append(entry);
        with open(self.path, "a") as handle:
            handle.write(json.dumps(entry) + "\n");
