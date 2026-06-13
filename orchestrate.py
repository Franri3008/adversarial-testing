import os
import json
from typing import Any, Dict, List

from fixtures.buggy import BUGGY_SRC, ONESHOT_SRC, PLANTED_BUGS, REFERENCE_SRC
from generator import generate_test
from harness import JsonlLogger, is_plateau
import repair_main as repair

LOG_PATH = "orchestrate_run.jsonl";
HARDEN_MAX = int(os.environ.get("ORCH_HARDEN_ITERS", "12"));
TOKEN_CAP = int(os.environ.get("ORCH_TOKEN_CAP", "0"));
ROLE_ORDER = ["bulk", "strategy"];


def _phase2_harden(code: str, suite_sources: List[str], start_tokens: int, logger: JsonlLogger) -> Dict[str, Any]:
    tokens = start_tokens;
    mutants = repair._discover_mutants(code);
    kill_rates = [];
    role_idx = 0;
    stop = "max-iterations";
    print("phase  iteration  cumulative_tokens  tier      kill_rate  surviving");
    for iteration in range(1, HARDEN_MAX + 1):
        kill_rate, surviving = repair._measure_kill_rate(code, suite_sources, mutants);
        kill_rates.append(kill_rate);
        entry = {
            "phase": "harden",
            "iteration": iteration,
            "cumulative_tokens": tokens,
            "tier": ROLE_ORDER[role_idx],
            "kill_rate": kill_rate,
            "surviving": len(surviving),
        };
        logger.append(entry);
        print("harden  {:>9}  {:>17}  {:<8}  {:>9.3f}  {}".format(iteration, tokens, ROLE_ORDER[role_idx], kill_rate, len(surviving)));

        if not surviving:
            stop = "full-kill";
            break
        if TOKEN_CAP and tokens >= TOKEN_CAP:
            stop = "budget-cap";
            break
        if is_plateau(kill_rates):
            if role_idx < len(ROLE_ORDER) - 1:
                role_idx += 1;
                print("plateau -> escalate tier to {}".format(ROLE_ORDER[role_idx]));
            else:
                stop = "plateau";
                break

        gen = generate_test(code, surviving, role=ROLE_ORDER[role_idx]);
        tokens += gen["tokens"]["in"] + gen["tokens"]["out"];
        new_test = gen["test_src"];
        if repair._passes_on_correct(new_test, code):
            suite_sources.append(repair._mangle(new_test, "p2_{}".format(iteration)));
    final_kill_rate = kill_rates[-1] if kill_rates else 0.0;
    return {"cumulative_tokens": tokens, "kill_rate": final_kill_rate, "stop": stop}


def main() -> None:
    logger = JsonlLogger(LOG_PATH);

    print("=== PHASE 1: REPAIR (find & fix real bugs) ===");
    repaired = repair.run_repair(BUGGY_SRC, REFERENCE_SRC, PLANTED_BUGS, verbose=True, oneshot_src=ONESHOT_SRC);
    for entry in repaired["entries"]:
        merged = dict(entry);
        merged["phase"] = "repair";
        logger.append(merged);

    print("");
    print("=== PHASE 2: HARDEN (mutation-test the repaired code to plateau) ===");
    suite_sources = list(repaired["suite_sources"]);
    hardened = _phase2_harden(repaired["final_code"], suite_sources, repaired["cumulative_tokens"], logger);

    print("");
    print("=== ORCHESTRATION COMPLETE ===");
    print("repaired {}/{} planted bugs".format(repaired["graded"], repaired["total_bugs"]));
    print("final suite kill-rate {:.3f} ({} tests, stop: {})".format(hardened["kill_rate"], len(suite_sources), hardened["stop"]));
    print("total tokens {} (repair {} + harden {})".format(hardened["cumulative_tokens"], repaired["cumulative_tokens"], hardened["cumulative_tokens"] - repaired["cumulative_tokens"]));
    print("log at {}".format(LOG_PATH));


if __name__ == "__main__":
    main();
