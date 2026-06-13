from fixtures import MUTANTS, REFERENCE_SRC
from generator import generate_test
from harness import JsonlLogger, compute_kill_rate, is_plateau, make_log_entry, run_baseline
from runner import run_and_check

MAX_ITERATIONS = 25
LOG_PATH = "run.jsonl"


def main() -> None:
    logger = JsonlLogger(LOG_PATH);
    total = len(MUTANTS);

    baseline = run_baseline(REFERENCE_SRC, MUTANTS, generate_test, run_and_check);
    print("baseline kill_rate={:.3f} tokens={}".format(baseline["kill_rate"], baseline["cumulative_tokens"]));

    surviving = list(MUTANTS);
    killed_total = set();
    cumulative_tokens = 0;
    kill_rates = [];

    print("iteration  cumulative_tokens  kill_rate  killed_this_round");
    for iteration in range(1, MAX_ITERATIONS + 1):
        gen = generate_test(REFERENCE_SRC, surviving);
        cumulative_tokens += gen["tokens"]["in"] + gen["tokens"]["out"];

        result = run_and_check(gen["test_src"], REFERENCE_SRC, surviving);
        killed_this_round = result["killed_mutant_ids"] if result["reference_passed"] else [];
        for mid in killed_this_round:
            killed_total.add(mid);
        surviving = [m for m in surviving if m["id"] not in killed_total];

        kill_rate = compute_kill_rate(len(killed_total), total);
        kill_rates.append(kill_rate);

        entry = make_log_entry(iteration, cumulative_tokens, kill_rate, killed_this_round);
        logger.append(entry);
        print("{:>9}  {:>17}  {:>9.3f}  {}".format(iteration, cumulative_tokens, kill_rate, killed_this_round));

        if is_plateau(kill_rates):
            print("plateau detected at iteration {}".format(iteration));
            break

    print("final kill_rate={:.3f} over {} mutants, log at {}".format(kill_rates[-1], total, LOG_PATH));


if __name__ == "__main__":
    main()
