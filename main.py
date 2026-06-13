import os
import sys
from typing import Dict, List, Optional

from generator import generate_test
from harness import JsonlLogger, compute_kill_rate, is_plateau, make_log_entry, run_baseline

MAX_ITERATIONS = int(os.environ.get("MAX_ITERATIONS", "25"))
LOG_PATH = "run.jsonl"

# Two-tier stacked loop: start cheap (bulk), escalate to the smart model (strategy)
# when the cheap tier stops making progress. Budget caps are the terminal stop.
ROLE_ORDER = ["bulk", "strategy"]
COST_CAP_USD = float(os.environ.get("COST_CAP", "5.0"))      # 0 disables
TOKEN_CAP = int(os.environ.get("TOKEN_CAP", "0"))            # 0 disables

# Co-evolution: once the suite kills every current mutant, the adversary invents NEW
# bugs the suite misses, and the loop continues. This is what makes the looping the
# story — tokens keep buying coverage until the adversary is defeated. 0 rounds = the
# old one-shot behaviour (harden a fixed mutant set, then stop).
MUTANT_ROUNDS = int(os.environ.get("MUTANT_ROUNDS", "3"))
MUTANTS_PER_ROUND = int(os.environ.get("MUTANTS_PER_ROUND", "5"))


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


def harden_target(reference_src, mutants, language, function_name, test_import_path=None,
                  runner=None, log_path=LOG_PATH, label=""):
    """Run the two-tier harden loop on one target. Returns everything the report needs."""
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

    logger = JsonlLogger(log_path)
    total = len(mutants)

    baseline = run_baseline(reference_src, mutants, gen_fn, run_and_check)
    head = "[{}] ".format(label) if label else ""
    print("{}baseline kill_rate={:.3f} tokens={}".format(head, baseline["kill_rate"], baseline["cumulative_tokens"]))

    import adversary

    all_mutants = list(mutants)
    existing_ids = set(m["id"] for m in all_mutants)
    surviving = list(mutants)
    killed_total = set()
    cumulative_tokens = 0
    cumulative_cost = 0.0
    kill_rates = []
    role_idx = 0
    suite_sources = []
    strategy_model = ""
    bulk_model = ""
    mutant_round = 0

    def _over_budget():
        return (COST_CAP_USD and cumulative_cost >= COST_CAP_USD) or (TOKEN_CAP and cumulative_tokens >= TOKEN_CAP)

    print("iter  tier      cum_tokens   cost$    kill_rate  killed_this_round")
    stop = "max-iterations"
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

        entry = make_log_entry(iteration, cumulative_tokens, kill_rate, killed_this_round)
        entry["tier"] = role
        entry["cost_usd"] = round(cumulative_cost, 4)
        entry["mutant_round"] = mutant_round
        entry["total_mutants"] = total
        entry["killed_cumulative"] = len(killed_total)
        logger.append(entry)
        print("{:>4}  {:<8}  {:>10}  {:>6.3f}  {:>9.3f}  {}".format(
            iteration, role, cumulative_tokens, cumulative_cost, kill_rate, killed_this_round))

        # STOP: budget caps (the non-negotiable terminal condition).
        if _over_budget():
            stop = "budget-cap"
            print("budget cap reached -> stop")
            break

        # WAVE CLEARED: the suite kills every current mutant. Instead of stopping, send
        # in the adversary to invent new bugs the suite misses — the arms race continues.
        if not surviving:
            if mutant_round >= MUTANT_ROUNDS:
                stop = "rounds-exhausted"
                print("all {} mutants killed; adversary budget ({} rounds) spent -> stop".format(total, MUTANT_ROUNDS))
                break
            mutant_round += 1
            print("--- wave {} cleared ({} mutants killed) -> adversary searching for new bugs ---".format(mutant_round, total))
            adv = adversary.generate_surviving_mutants(
                reference_src, function_name, language, suite_sources, run_and_check,
                n=MUTANTS_PER_ROUND, existing_ids=existing_ids, round_idx=mutant_round, role="strategy")
            cumulative_tokens += adv["tokens"]
            cumulative_cost += adv.get("cost", 0.0)
            strategy_model = adv.get("model", strategy_model) or strategy_model
            if not adv["mutants"]:
                stop = "adversary-defeated"
                print("adversary found NO surviving mutant -> suite is robust, plateau at 100%")
                break
            all_mutants.extend(adv["mutants"])
            surviving = list(adv["mutants"])
            total = len(all_mutants)
            role_idx = 0          # fresh wave: start cheap again
            kill_rates = []
            print("adversary round {}: +{} new surviving mutants ({} total) -> {}".format(
                mutant_round, len(adv["mutants"]), total, [m["id"] for m in adv["mutants"]]))
            continue

        # PLATEAU: don't just quit — escalate cheap->smart, then quit only if the
        # strongest tier also plateaus. This is the stacked loop made literal.
        if is_plateau(kill_rates):
            if role_idx + 1 < len(ROLE_ORDER):
                role_idx += 1
                print("plateau on '{}' ({} surviving) -> escalating to '{}'".format(
                    role, len(surviving), ROLE_ORDER[role_idx]))
                kill_rates = []  # give the stronger tier a fresh plateau window
            else:
                stop = "defender-plateau"
                print("plateau on strongest tier '{}' -> stop ({} unkilled)".format(
                    role, len(surviving)))
                break

    final = compute_kill_rate(len(killed_total), total)
    print("{}final: killed {}/{} mutants over {} adversary round(s), cost=${:.4f} ({})".format(
        head, len(killed_total), total, mutant_round, cumulative_cost, stop))
    return {
        "entries": logger.entries,
        "suite_sources": suite_sources,
        "baseline": baseline,
        "surviving": surviving,
        "final": final,
        "total": total,
        "mutant_rounds": mutant_round,
        "killed_total": len(killed_total),
        "stop": stop,
        "language": language,
        "function_name": function_name,
        "strategy_model": strategy_model or "-",
        "bulk_model": bulk_model or "-",
    }


def _run_repo_scan(kwargs: Dict[str, str]) -> None:
    """repo= given without function= -> discover every self-contained function and harden each."""
    import discover
    import report

    n = int(kwargs.get("mutants", "5"))
    max_targets = int(kwargs.get("max_targets", "0"))
    targets = discover.discover_targets(
        kwargs["repo"], mutants_per=n, max_targets=max_targets, only_file=kwargs.get("file"))
    if not targets:
        raise SystemExit("no eligible self-contained functions found in {}".format(kwargs["repo"]))

    results = []
    for index, (rel, t) in enumerate(targets, start=1):
        label = "{}/{} {}::{}".format(index, len(targets), rel, t.function_name)
        print("\n=== TARGET {} ===".format(label))
        res = harden_target(
            t.reference_src, t.mutants, t.language, t.function_name,
            log_path="run_{:02d}.jsonl".format(index), label="{}::{}".format(rel, t.function_name))
        res["file"] = rel
        results.append(res)

    report_path = report.write_repo_report(kwargs["repo"], results)
    print("\nrepo report at {}".format(report_path))


def main() -> None:
    kwargs = _parse_kwargs(sys.argv[1:])

    # repo without an explicit function -> scan the whole repo for targets.
    if kwargs.get("repo") and not kwargs.get("function"):
        _run_repo_scan(kwargs)
        return

    reference_src, mutants, language, function_name, runner, test_import_path = resolve_target(kwargs)
    res = harden_target(reference_src, mutants, language, function_name, test_import_path, runner)

    import report
    meta = {
        "repo": kwargs.get("repo", "(built-in fixture)"),
        "file": kwargs.get("file", "-"),
        "function": function_name or kwargs.get("function", "-"),
        "language": language,
        "strategy_model": res["strategy_model"],
        "bulk_model": res["bulk_model"],
        "total_mutants": res["total"],
        "surviving": res["surviving"],
        "mutant_rounds": res.get("mutant_rounds", 0),
        "killed_total": res.get("killed_total", 0),
    }
    report_path = report.write_report(meta, res["entries"], res["suite_sources"], baseline=res["baseline"])
    print("report at {}".format(report_path))


if __name__ == "__main__":
    main()
