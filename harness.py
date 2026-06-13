import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

LOG_FIELDS = ["iteration", "cumulative_tokens", "kill_rate", "killed_this_round"]


def new_run_id() -> str:
    return uuid.uuid4().hex


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _base_event(
    event: str,
    run_id: Optional[str] = None,
    phase: Optional[str] = None,
    iteration: Optional[int] = None,
    status: Optional[str] = None,
    cumulative_tokens: Optional[int] = None,
    cost_usd: Optional[float] = None,
    **fields: Any,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "event": event,
        "run_id": run_id or new_run_id(),
        "timestamp": _timestamp(),
    }
    if phase is not None:
        entry["phase"] = phase
    if iteration is not None:
        entry["iteration"] = iteration
    if status is not None:
        entry["status"] = status
    if cumulative_tokens is not None:
        entry["cumulative_tokens"] = cumulative_tokens
    if cost_usd is not None:
        entry["cost_usd"] = round(cost_usd, 4)
    entry.update(fields)
    return entry


def _mutant_record(mutant: Dict[str, Any], status: str = "generated") -> Dict[str, Any]:
    return {
        "id": mutant.get("id", ""),
        "description": mutant.get("description", ""),
        "src": mutant.get("src", ""),
        "status": mutant.get("status", status),
    }


def mutant_records(mutants: List[Dict[str, Any]], status: str = "generated") -> List[Dict[str, Any]]:
    return [_mutant_record(mutant, status=status) for mutant in mutants]


def run_started(run_id: str, phase: str, target: Dict[str, Any], reference_src: str = "") -> Dict[str, Any]:
    return _base_event(
        "run_started",
        run_id=run_id,
        phase=phase,
        status="running",
        target=target,
        reference_src=reference_src,
    )


def mutants_generated(run_id: str, phase: str, mutants: List[Dict[str, Any]], iteration: Optional[int] = None) -> Dict[str, Any]:
    return _base_event(
        "mutants_generated",
        run_id=run_id,
        phase=phase,
        iteration=iteration,
        status="generated",
        total_mutants=len(mutants),
        mutants=mutant_records(mutants),
    )


def iteration_completed(
    run_id: str,
    phase: str,
    iteration: int,
    cumulative_tokens: int,
    kill_rate: float,
    killed_this_round: List[str],
    surviving_mutants: List[Dict[str, Any]],
    status: str = "completed",
    cost_usd: Optional[float] = None,
    **fields: Any,
) -> Dict[str, Any]:
    return _base_event(
        "iteration_completed",
        run_id=run_id,
        phase=phase,
        iteration=iteration,
        status=status,
        cumulative_tokens=cumulative_tokens,
        cost_usd=cost_usd,
        kill_rate=kill_rate,
        killed_this_round=list(killed_this_round),
        surviving_mutant_ids=[mutant.get("id", "") for mutant in surviving_mutants],
        surviving_mutants=mutant_records(surviving_mutants, status="surviving"),
        **fields,
    )


def fix_attempted(
    run_id: str,
    phase: str,
    iteration: int,
    bug: Dict[str, Any],
    attempt: int,
    generated_test_src: str,
    proposed_fixed_src: str,
    cumulative_tokens: int,
) -> Dict[str, Any]:
    return _base_event(
        "fix_attempted",
        run_id=run_id,
        phase=phase,
        iteration=iteration,
        status="attempted",
        cumulative_tokens=cumulative_tokens,
        bug=bug,
        attempt=attempt,
        generated_test_src=generated_test_src,
        proposed_fixed_src=proposed_fixed_src,
    )


def bug_selected(
    run_id: str,
    phase: str,
    iteration: int,
    has_bug: bool,
    bug: Optional[Dict[str, Any]],
    cumulative_tokens: int,
) -> Dict[str, Any]:
    return _base_event(
        "bug_selected",
        run_id=run_id,
        phase=phase,
        iteration=iteration,
        status="selected" if has_bug else "no_bug",
        cumulative_tokens=cumulative_tokens,
        has_bug=has_bug,
        bug=bug,
    )


def fix_accepted(
    run_id: str,
    phase: str,
    iteration: int,
    bug: Dict[str, Any],
    generated_test_src: str,
    final_code: str,
    cumulative_tokens: int,
) -> Dict[str, Any]:
    return _base_event(
        "fix_accepted",
        run_id=run_id,
        phase=phase,
        iteration=iteration,
        status="accepted",
        cumulative_tokens=cumulative_tokens,
        bug=bug,
        generated_test_src=generated_test_src,
        final_code=final_code,
    )


def fix_rejected(
    run_id: str,
    phase: str,
    iteration: int,
    bug: Dict[str, Any],
    reason: str,
    cumulative_tokens: int,
    generated_test_src: str = "",
    proposed_fixed_src: str = "",
) -> Dict[str, Any]:
    return _base_event(
        "fix_rejected",
        run_id=run_id,
        phase=phase,
        iteration=iteration,
        status="rejected",
        cumulative_tokens=cumulative_tokens,
        bug=bug,
        reason=reason,
        generated_test_src=generated_test_src,
        proposed_fixed_src=proposed_fixed_src,
    )


def hardening_completed(
    run_id: str,
    phase: str,
    iteration: int,
    cumulative_tokens: int,
    kill_rate: float,
    mutants: List[Dict[str, Any]],
    surviving_mutants: List[Dict[str, Any]],
    generated_tests: List[str],
) -> Dict[str, Any]:
    surviving_ids = {mutant.get("id") for mutant in surviving_mutants}
    marked = []
    for mutant in mutants:
        status = "surviving" if mutant.get("id") in surviving_ids else "killed"
        marked.append(_mutant_record(mutant, status=status))
    return _base_event(
        "hardening_completed",
        run_id=run_id,
        phase=phase,
        iteration=iteration,
        status="completed",
        cumulative_tokens=cumulative_tokens,
        kill_rate=kill_rate,
        mutants=marked,
        surviving_mutant_ids=[mutant.get("id", "") for mutant in surviving_mutants],
        surviving_mutants=mutant_records(surviving_mutants, status="surviving"),
        generated_tests=list(generated_tests),
    )


def run_finished(
    run_id: str,
    phase: str,
    status: str,
    stop_reason: str,
    cumulative_tokens: int,
    kill_rate: float = 0.0,
    cost_usd: Optional[float] = None,
    final_code: str = "",
    **fields: Any,
) -> Dict[str, Any]:
    return _base_event(
        "run_finished",
        run_id=run_id,
        phase=phase,
        status=status,
        cumulative_tokens=cumulative_tokens,
        cost_usd=cost_usd,
        stop_reason=stop_reason,
        kill_rate=kill_rate,
        final_code=final_code,
        **fields,
    )


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
    def __init__(self, path: str, run_id: Optional[str] = None):
        self.path = path;
        self.run_id = run_id or new_run_id();
        self.entries = [];
        open(self.path, "w").close();

    def append(self, entry: Dict[str, Any]) -> None:
        self.entries.append(entry);
        with open(self.path, "a") as handle:
            handle.write(json.dumps(entry) + "\n");
