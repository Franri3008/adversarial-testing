import os
import sys
from typing import Dict, List, Optional

from generator import generate_test
from harness import (
    JsonlLogger,
    compute_kill_rate,
    is_plateau,
    iteration_completed,
    make_log_entry,
    mutant_records,
    mutants_generated,
    run_baseline,
    run_finished,
    run_started,
)

MAX_ITERATIONS = int(os.environ.get("MAX_ITERATIONS", "25"))
LOG_PATH = "run.jsonl"

# Two-tier stacked loop: start cheap (bulk), escalate to the smart model (strategy)
# when the cheap tier stops making progress. Budget caps are the terminal stop.
ROLE_ORDER = ["bulk", "strategy"]
COST_CAP_USD = float(os.environ.get("COST_CAP", "5.0"))      # 0 disables
TOKEN_CAP = int(os.environ.get("TOKEN_CAP", "0"))            # 0 disables


def _parse_kwargs(argv: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for arg in argv:
        if "=" in arg:
            key, _, value = arg.partition("=")
            out[key.strip()] = value.strip()
    return out


def resolve_target(kwargs: Dict[str, str]):
    """CLI mode (repo=/file=/function=) acquires a target from a real repo;
    otherwise fall back to a built-in fixture (FIXTURE)."""
    if kwargs.get("repo") or kwargs.get("file"):
        from acquire import acquire_target

        missing = [k for k in ("repo", "file", "function") if not kwargs.get(k)]
        if missing:
            raise SystemExit(f"CLI mode needs: repo=, file=, function= (missing: {missing})")
        n = int(kwargs.get("mutants", "5"))
        t = acquire_target(kwargs["repo"], kwargs["file"], kwargs["function"], n)
        return t.reference_src, t.mutants, t.language, t.function_name, None, None

    import fixtures

    return (
        fixtures.REFERENCE_SRC,
        fixtures.MUTANTS,
        fixtures.LANGUAGE,
        fixtures.FUNCTION_NAME,
        getattr(fixtures, "RUNNER", None),
        getattr(fixtures, "TEST_IMPORT_PATH", None),
    )


def _get_runner(language: str, runner: Optional[str] = None):
    if runner == "typescript_repo":
        from runner_repo_ts import run_and_check
    elif language == "typescript":
        from runner_ts import run_and_check
    else:
        from runner import run_and_check
    return run_and_check


def main() -> None:
    kwargs = _parse_kwargs(sys.argv[1:])
    reference_src, mutants, language, function_name, runner, test_import_path = resolve_target(kwargs)
    run_and_check = _get_runner(language, runner)

    # Bind language/function so generation works for both fixture and CLI targets.
    def gen_fn(ref, surviving, role="bulk"):
        return generate_test(
            ref,
            surviving,
            role=role,
            language=language,
            function_name=function_name,
            test_import_path=test_import_path,
        )

    logger = JsonlLogger(LOG_PATH)
    total = len(mutants)
    target = {
        "repo": kwargs.get("repo", "(built-in fixture)"),
        "file": kwargs.get("file", "-"),
        "function": function_name or kwargs.get("function", "-"),
        "language": language,
    }
    logger.append(run_started(logger.run_id, "harden", target, reference_src=reference_src))
    logger.append(mutants_generated(logger.run_id, "harden", mutants))

    baseline = run_baseline(reference_src, mutants, gen_fn, run_and_check)
    print("baseline kill_rate={:.3f} tokens={}".format(baseline["kill_rate"], baseline["cumulative_tokens"]))

    surviving = list(mutants)
    killed_total = set()
    cumulative_tokens = 0
    cumulative_cost = 0.0
    kill_rates = []
    role_idx = 0
    suite_sources = []
    strategy_model = ""
    bulk_model = ""
    stop_reason = "max_iterations"

    print("iter  tier      cum_tokens   cost$    kill_rate  killed_this_round")
    for iteration in range(1, MAX_ITERATIONS + 1):
        role = ROLE_ORDER[role_idx]
        gen = gen_fn(reference_src, surviving, role=role)
        cumulative_tokens += gen["tokens"]["in"] + gen["tokens"]["out"]
        cumulative_cost += gen.get("cost", 0.0)

        bulk_model = gen.get("model", bulk_model) if role == "bulk" else bulk_model
        strategy_model = gen.get("model", strategy_model) if role == "strategy" else strategy_model

        result = run_and_check(gen["test_src"], reference_src, surviving)
        killed_this_round = result["killed_mutant_ids"] if result["reference_passed"] else []
        if result["reference_passed"] and killed_this_round:
            suite_sources.append(gen["test_src"])
        for mid in killed_this_round:
            killed_total.add(mid)
        surviving = [m for m in surviving if m["id"] not in killed_total]

        kill_rate = compute_kill_rate(len(killed_total), total)
        kill_rates.append(kill_rate)

        killed_mutants = [m for m in mutants if m["id"] in set(killed_this_round)]
        entry = iteration_completed(
            logger.run_id,
            "harden",
            iteration,
            cumulative_tokens,
            kill_rate,
            killed_this_round,
            surviving,
            cost_usd=cumulative_cost,
            tier=role,
            generated_test_src=gen["test_src"],
            reference_passed=result["reference_passed"],
            killed_mutants=mutant_records(killed_mutants, status="killed"),
        )
        entry.update(make_log_entry(iteration, cumulative_tokens, kill_rate, killed_this_round))
        entry["tier"] = role
        entry["cost_usd"] = round(cumulative_cost, 4)
        logger.append(entry)
        print("{:>4}  {:<8}  {:>10}  {:>6.3f}  {:>9.3f}  {}".format(
            iteration, role, cumulative_tokens, cumulative_cost, kill_rate, killed_this_round))

        # STOP: every mutant killed — the loop has fully succeeded.
        if not surviving:
            stop_reason = "all_killed"
            print("all {} mutants killed at iteration {}".format(total, iteration))
            break

        # STOP: budget caps (the non-negotiable terminal condition).
        if COST_CAP_USD and cumulative_cost >= COST_CAP_USD:
            stop_reason = "cost_cap"
            print("cost cap ${:.2f} reached -> stop".format(COST_CAP_USD))
            break
        if TOKEN_CAP and cumulative_tokens >= TOKEN_CAP:
            stop_reason = "token_cap"
            print("token cap {} reached -> stop".format(TOKEN_CAP))
            break

        # PLATEAU: don't just quit — escalate cheap->smart, then quit only if the
        # strongest tier also plateaus. This is the stacked loop made literal.
        if is_plateau(kill_rates):
            if role_idx + 1 < len(ROLE_ORDER):
                role_idx += 1
                print("plateau on '{}' ({} surviving) -> escalating to '{}'".format(
                    role, len(surviving), ROLE_ORDER[role_idx]))
                kill_rates = []  # give the stronger tier a fresh plateau window
            else:
                stop_reason = "plateau"
                print("plateau on strongest tier '{}' -> stop ({} unkilled)".format(
                    role, len(surviving)))
                break

    final = compute_kill_rate(len(killed_total), total)
    logger.append(run_finished(
        logger.run_id,
        "harden",
        "completed" if final >= 1.0 else "stopped",
        stop_reason,
        cumulative_tokens,
        kill_rate=final,
        cost_usd=cumulative_cost,
        total_mutants=total,
        killed_mutant_ids=sorted(killed_total),
        surviving_mutants=mutant_records(surviving, status="surviving"),
    ))
    print("final kill_rate={:.3f} over {} mutants, cost=${:.4f}, log at {}".format(
        final, total, cumulative_cost, LOG_PATH))

    import report
    meta = {
        **target,
        "strategy_model": strategy_model or "-",
        "bulk_model": bulk_model or "-",
        "total_mutants": total,
        "surviving": surviving,
        "stop_reason": stop_reason,
    }
    report_path = report.write_report(meta, logger.entries, suite_sources, baseline=baseline)
    print("report at {}".format(report_path))


if __name__ == "__main__":
    main()
