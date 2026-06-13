import os
import sys
from typing import Dict, List

from generator import generate_test
from harness import JsonlLogger, compute_kill_rate, is_plateau, make_log_entry, run_baseline

MAX_ITERATIONS = int(os.environ.get("LOOPIFY_MAX_ITERATIONS", "25"))
LOG_PATH = "run.jsonl"

# Two-tier stacked loop: start cheap (bulk), escalate to the smart model (strategy)
# when the cheap tier stops making progress. Budget caps are the terminal stop.
ROLE_ORDER = ["bulk", "strategy"]
COST_CAP_USD = float(os.environ.get("LOOPIFY_COST_CAP", "5.0"))      # 0 disables
TOKEN_CAP = int(os.environ.get("LOOPIFY_TOKEN_CAP", "0"))            # 0 disables


def _parse_kwargs(argv: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for arg in argv:
        if "=" in arg:
            key, _, value = arg.partition("=")
            out[key.strip()] = value.strip()
    return out


def _resolve_target():
    """CLI mode (repo=/file=/function=) acquires a target from a real repo;
    otherwise fall back to a built-in fixture (LOOPIFY_FIXTURE)."""
    kwargs = _parse_kwargs(sys.argv[1:])
    if kwargs.get("repo") or kwargs.get("file"):
        from acquire import acquire_target

        missing = [k for k in ("repo", "file", "function") if not kwargs.get(k)]
        if missing:
            raise SystemExit(f"CLI mode needs: repo=, file=, function= (missing: {missing})")
        n = int(kwargs.get("mutants", "5"))
        t = acquire_target(kwargs["repo"], kwargs["file"], kwargs["function"], n)
        return t.reference_src, t.mutants, t.language, t.function_name

    import fixtures

    return fixtures.REFERENCE_SRC, fixtures.MUTANTS, fixtures.LANGUAGE, fixtures.FUNCTION_NAME


def _get_runner(language: str):
    if language == "typescript":
        from runner_ts import run_and_check
    else:
        from runner import run_and_check
    return run_and_check


def main() -> None:
    reference_src, mutants, language, function_name = _resolve_target()
    run_and_check = _get_runner(language)

    # Bind language/function so generation works for both fixture and CLI targets.
    def gen_fn(ref, surviving, role="bulk"):
        return generate_test(ref, surviving, role=role, language=language, function_name=function_name)

    logger = JsonlLogger(LOG_PATH)
    total = len(mutants)

    baseline = run_baseline(reference_src, mutants, gen_fn, run_and_check)
    print("baseline kill_rate={:.3f} tokens={}".format(baseline["kill_rate"], baseline["cumulative_tokens"]))

    surviving = list(mutants)
    killed_total = set()
    cumulative_tokens = 0
    cumulative_cost = 0.0
    kill_rates = []
    role_idx = 0

    print("iter  tier      cum_tokens   cost$    kill_rate  killed_this_round")
    for iteration in range(1, MAX_ITERATIONS + 1):
        role = ROLE_ORDER[role_idx]
        gen = gen_fn(reference_src, surviving, role=role)
        cumulative_tokens += gen["tokens"]["in"] + gen["tokens"]["out"]
        cumulative_cost += gen.get("cost", 0.0)

        result = run_and_check(gen["test_src"], reference_src, surviving)
        killed_this_round = result["killed_mutant_ids"] if result["reference_passed"] else []
        for mid in killed_this_round:
            killed_total.add(mid)
        surviving = [m for m in surviving if m["id"] not in killed_total]

        kill_rate = compute_kill_rate(len(killed_total), total)
        kill_rates.append(kill_rate)

        entry = make_log_entry(iteration, cumulative_tokens, kill_rate, killed_this_round)
        entry["tier"] = role
        entry["cost_usd"] = round(cumulative_cost, 4)
        logger.append(entry)
        print("{:>4}  {:<8}  {:>10}  {:>6.3f}  {:>9.3f}  {}".format(
            iteration, role, cumulative_tokens, cumulative_cost, kill_rate, killed_this_round))

        # STOP: every mutant killed — the loop has fully succeeded.
        if not surviving:
            print("all {} mutants killed at iteration {}".format(total, iteration))
            break

        # STOP: budget caps (the non-negotiable terminal condition).
        if COST_CAP_USD and cumulative_cost >= COST_CAP_USD:
            print("cost cap ${:.2f} reached -> stop".format(COST_CAP_USD))
            break
        if TOKEN_CAP and cumulative_tokens >= TOKEN_CAP:
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
                print("plateau on strongest tier '{}' -> stop ({} unkilled)".format(
                    role, len(surviving)))
                break

    final = compute_kill_rate(len(killed_total), total)
    print("final kill_rate={:.3f} over {} mutants, cost=${:.4f}, log at {}".format(
        final, total, cumulative_cost, LOG_PATH))


if __name__ == "__main__":
    main()
