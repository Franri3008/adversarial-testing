import os

from fixtures import LANGUAGE, MUTANTS, REFERENCE_SRC
from generator import generate_test
from harness import JsonlLogger, compute_kill_rate, is_plateau, make_log_entry, run_baseline

# Verifier is selected by the fixture's language: Python -> pytest, TypeScript -> vitest.
if LANGUAGE == "typescript":
    from runner_ts import run_and_check
else:
    from runner import run_and_check

MAX_ITERATIONS = int(os.environ.get("LOOPIFY_MAX_ITERATIONS", "25"))
LOG_PATH = "run.jsonl"

# Two-tier stacked loop: start cheap (bulk), escalate to the smart model (strategy)
# when the cheap tier stops making progress. Budget caps are the terminal stop.
ROLE_ORDER = ["bulk", "strategy"]
COST_CAP_USD = float(os.environ.get("LOOPIFY_COST_CAP", "5.0"))      # 0 disables
TOKEN_CAP = int(os.environ.get("LOOPIFY_TOKEN_CAP", "0"))            # 0 disables


def main() -> None:
    logger = JsonlLogger(LOG_PATH)
    total = len(MUTANTS)

    baseline = run_baseline(REFERENCE_SRC, MUTANTS, generate_test, run_and_check)
    print("baseline kill_rate={:.3f} tokens={}".format(baseline["kill_rate"], baseline["cumulative_tokens"]))

    surviving = list(MUTANTS)
    killed_total = set()
    cumulative_tokens = 0
    cumulative_cost = 0.0
    kill_rates = []
    role_idx = 0

    print("iter  tier      cum_tokens   cost$    kill_rate  killed_this_round")
    for iteration in range(1, MAX_ITERATIONS + 1):
        role = ROLE_ORDER[role_idx]
        gen = generate_test(REFERENCE_SRC, surviving, role=role)
        cumulative_tokens += gen["tokens"]["in"] + gen["tokens"]["out"]
        cumulative_cost += gen.get("cost", 0.0)

        result = run_and_check(gen["test_src"], REFERENCE_SRC, surviving)
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
