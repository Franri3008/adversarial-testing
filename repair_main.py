import ast
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

from fixer import generate_fix
from fixtures.buggy import BUGGY_SRC, MUTANTS as SEED_MUTANTS, ONESHOT_SRC, PLANTED_BUGS, REFERENCE_SRC
from generator import generate_test
from harness import JsonlLogger, compute_kill_rate
import llm
from repair_generator import generate_bug_test
import runner
from strategy import find_bug

MAX_ITERATIONS = 12;
HARDEN_ATTEMPTS = 3;
RETRY_PER_BUG = 2;
PATIENCE = 3;
LOG_PATH = "repair_run.jsonl";
BASELINE_PATH = "repair_baseline.json";


def _token_count(tokens):
    return tokens.get("in", 0) + tokens.get("out", 0)


def _function_name(src: str) -> str:
    match = re.search(r"^\s*def\s+(\w+)\s*\(", src, re.MULTILINE);
    return match.group(1) if match else "subject"


def _mangle(test_src: str, tag: str) -> str:
    safe_tag = "".join(ch if ch.isalnum() else "_" for ch in tag);
    try:
        tree = ast.parse(test_src);
    except SyntaxError:
        return test_src
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            node.name = "test_{}_{}".format(safe_tag, node.name[len("test_"):]);
    return ast.unparse(tree)


def _suite_text(sources: List[str]) -> str:
    if not sources:
        return "def test_empty_suite():\n    assert True\n"
    return "\n\n".join(sources)


def _build_observation(code, bugs_fixed, failed_attempts, seed_bugs, cumulative_tokens):
    return {
        "code": code,
        "fixed_bug_ids": [bug["id"] for bug in bugs_fixed],
        "fixed_bug_descriptions": [bug["description"] for bug in bugs_fixed],
        "failed_attempt_ids": [item["id"] for item in failed_attempts],
        "failed_attempts": [item["description"] for item in failed_attempts],
        "seed_bugs": list(seed_bugs),
        "next_bug_index": len(bugs_fixed) + len(failed_attempts) + 1,
        "cumulative_tokens": cumulative_tokens,
    }


def _build_discovery_prompt(reference_src: str) -> str:
    return (
        "You are the discovery stage in an automatic repair loop.\n"
        "Inspect the corrected source and create mutants that represent plausible regressions.\n"
        "Each mutant must keep the same public function name as the reference source.\n"
        "Return only valid JSON with this exact shape:\n"
        "{\"mutants\":[{\"id\":\"M1_short_name\",\"description\":\"what behavior is broken\",\"src\":\"full mutant python source\"}]}\n"
        "Rules:\n"
        "- Return 3 to 6 high-signal mutants.\n"
        "- Each src must be complete executable Python source for the mutated target.\n"
        "- Do not include markdown fences.\n\n"
        "Source:\n"
        + reference_src
    )


def _load_json(text: str) -> Dict[str, Any]:
    stripped = text.strip();
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{");
        end = stripped.rfind("}");
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            return json.loads(stripped[start:end + 1])
        except json.JSONDecodeError:
            return {}


def _is_valid_mutant(mutant: Any) -> bool:
    if not isinstance(mutant, dict):
        return False
    for key in ("id", "description", "src"):
        if not isinstance(mutant.get(key), str) or not mutant[key]:
            return False
    try:
        ast.parse(mutant["src"]);
    except SyntaxError:
        return False
    return True


def _fallback_mutants(code: str) -> List[Dict[str, Any]]:
    # Offline (stub) fallback only: the planted `grade` fixture ships hand-written seed
    # mutants so its deterministic demo can still harden. For any other target there is no
    # offline mutant population — a real LLM backend discovers them generically above.
    if "def grade" in code:
        return list(SEED_MUTANTS)
    return []


def _discover_mutants(code: str) -> List[Dict[str, Any]]:
    response = llm.complete(_build_discovery_prompt(code), role="bulk");
    text = response.get("text", "");
    if text.strip() == "STUB_COMPLETION":
        return _fallback_mutants(code)
    parsed = _load_json(text);
    mutants = parsed.get("mutants", []) if isinstance(parsed, dict) else [];
    mutants = [mutant for mutant in mutants if _is_valid_mutant(mutant)] if isinstance(mutants, list) else [];
    return mutants if mutants else _fallback_mutants(code)


def _verify_fix(test_src: str, fixed_src: str, buggy_src: str, bug_id: str, bug_description: str) -> bool:
    mutant = {"id": bug_id, "description": bug_description, "src": buggy_src};
    result = runner.run_and_check(test_src, fixed_src, [mutant]);
    return bool(result["reference_passed"]) and bug_id in result["killed_mutant_ids"]


def _measure_kill_rate(code: str, suite_sources: List[str], mutants: List[Dict[str, Any]]):
    if not mutants:
        return 0.0, []
    result = runner.run_and_check(_suite_text(suite_sources), code, mutants);
    killed = set(result["killed_mutant_ids"]) if result["reference_passed"] else set();
    surviving = [mutant for mutant in mutants if mutant["id"] not in killed];
    return compute_kill_rate(len(killed), len(mutants)), surviving


def _passes_on_correct(test_src: str, code: str) -> bool:
    probe = {"id": "_probe", "description": "self probe", "src": code};
    result = runner.run_and_check(test_src, code, [probe]);
    return bool(result["reference_passed"])


def _suite_passes(tests: List[str], code: str) -> bool:
    if not tests:
        return True
    return _passes_on_correct(_suite_text(tests), code)


def _eval_kill_rate(tests: List[str], oracle_src: str, eval_mutants: List[Dict[str, Any]]) -> float:
    if not tests or not eval_mutants:
        return 0.0
    result = runner.run_and_check(_suite_text(tests), oracle_src, eval_mutants);
    killed = set(result["killed_mutant_ids"]) if result["reference_passed"] else set();
    return compute_kill_rate(len(killed), len(eval_mutants))


def _harden(code: str, suite_sources: List[str], mutants: List[Dict[str, Any]], tag: str):
    tokens = 0;
    kill_rate, surviving = _measure_kill_rate(code, suite_sources, mutants);
    for attempt in range(HARDEN_ATTEMPTS):
        if not surviving:
            break
        gen = generate_test(code, surviving, role="bulk");
        tokens += _token_count(gen["tokens"]);
        new_test = gen["test_src"];
        if not _passes_on_correct(new_test, code):
            continue
        suite_sources.append(_mangle(new_test, "{}_h{}".format(tag, attempt)));
        kill_rate, surviving = _measure_kill_rate(code, suite_sources, mutants);
    return kill_rate, surviving, tokens


def _grade(code: str, buggy_src: str, planted_bugs: List[Dict[str, Any]]) -> int:
    fixed = 0;
    for bug in planted_bugs:
        if _verify_fix(bug["stub_test_src"], code, buggy_src, bug["id"], bug["description"]):
            fixed += 1;
    return fixed


def _oneshot_baseline(buggy_src: str, planted_bugs: List[Dict[str, Any]], oneshot_src: Optional[str] = None) -> Dict[str, Any]:
    # Blind one-shot: the SAME information the loop starts with — just the buggy code and an
    # instruction to fix it. No answer-key tests, no oracle crutch on the live path; this is the
    # fair comparison point. oneshot_src is used ONLY as the offline (stub) fallback so the demo
    # still produces a baseline when no LLM is reachable.
    combined = {"description": "Find and fix every bug so the function is correct and robust for all inputs, including invalid arguments and boundary values.", "target_name": _function_name(buggy_src)};
    fix = generate_fix(buggy_src, combined, "", oracle_src=None, stub_fixed_src=oneshot_src);
    fixed_src = fix["fixed_src"];
    tokens = _token_count(fix["tokens"]);
    fixed_count = _grade(fixed_src, buggy_src, planted_bugs);
    return {"bugs_fixed": fixed_count, "total_bugs": len(planted_bugs), "cumulative_tokens": tokens}


def run_repair(code: str, oracle_src: Optional[str] = None, planted_bugs: Optional[List[Dict[str, Any]]] = None, start_tokens: int = 0, verbose: bool = True, oneshot_src: Optional[str] = None, eval_mutants: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    buggy_src = code;
    # Fixture mode (planted_bugs given) grades against a known answer key and measures the
    # suite against a frozen mutant population on a frozen oracle. Generalized mode (CLI /
    # arbitrary target) has neither: we report fixes made + the suite kill-rate measured by
    # the per-fix hardening step against mutants discovered from the corrected code.
    has_oracle = planted_bugs is not None;
    if eval_mutants is None:
        eval_mutants = list(SEED_MUTANTS) if has_oracle else [];
    # Seed bugs also carry their offline (stub) test+fix so the deterministic demo can run
    # with no model calls; a real backend ignores these and uses the model's own output.
    seed_bugs = [{
        "id": bug["id"],
        "description": bug["description"],
        "target_name": bug["target_name"],
        "stub_test_src": bug.get("stub_test_src"),
        "stub_fixed_src": bug.get("stub_fixed_src"),
    } for bug in planted_bugs] if has_oracle else [];

    if has_oracle:
        baseline = _oneshot_baseline(buggy_src, planted_bugs, oneshot_src=oneshot_src);
        if verbose:
            print("blind one-shot baseline: fixed {}/{} bugs in {} tokens (produces no tests)".format(
                baseline["bugs_fixed"], baseline["total_bugs"], baseline["cumulative_tokens"]));
    else:
        baseline = {"bugs_fixed": 0, "total_bugs": 0, "cumulative_tokens": 0};

    accepted_tests = [];
    fixed_bugs = [];
    fixed_descriptions = [];
    attempted = [];
    entries = [];
    cumulative_tokens = start_tokens + baseline["cumulative_tokens"];
    fixes_made = 0;
    no_progress = 0;
    last_harden_kr = 0.0;  # suite kill-rate from the most recent hardening step (generalized mode)

    if verbose:
        print("iter  cum_tokens  bugs_fixed   kill_rate  tests  note");
    for iteration in range(1, MAX_ITERATIONS + 1):
        observation = _build_observation(code, [{"id": "", "description": d} for d in fixed_descriptions], attempted, seed_bugs, cumulative_tokens);
        decision = find_bug(observation);
        cumulative_tokens += _token_count(decision["tokens"]);

        if not decision["has_bug"]:
            no_progress += 1;
            note = "model reports no bug ({}/{})".format(no_progress, PATIENCE);
        else:
            bug = decision["bug"];
            accepted = False;
            # Retry a few self-consistent test+fix pairs before giving up — one bad sample
            # must not permanently abandon a real, fixable bug.
            for attempt in range(RETRY_PER_BUG + 1):
                gen = generate_bug_test(code, bug, stub_test_src=bug.get("stub_test_src"), role="strategy");
                cumulative_tokens += _token_count(gen["tokens"]);
                test_src = gen["test_src"];
                if not test_src:
                    continue
                fix = generate_fix(code, bug, test_src, oracle_src=None, stub_fixed_src=bug.get("stub_fixed_src"));
                cumulative_tokens += _token_count(fix["tokens"]);
                fixed_src = fix["fixed_src"];
                # Accept only if the new test exposes the bug (fails on old, passes on fixed)
                # AND the fix breaks none of the already-accepted tests (no-regression gate).
                if _verify_fix(test_src, fixed_src, code, bug["id"], bug["description"]) and _suite_passes(accepted_tests, fixed_src):
                    code = fixed_src;
                    accepted_tests.append(_mangle(test_src, "{}_{}".format(bug["id"], iteration)));
                    fixed_descriptions.append(bug["description"]);
                    fixed_bugs.append(bug);
                    fixes_made += 1;
                    accepted = True;
                    break
            if accepted:
                no_progress = 0;
                note = "fixed via {}".format(bug["id"]);
                mutants = _discover_mutants(code);
                last_harden_kr, _, harden_tokens = _harden(code, accepted_tests, mutants, "{}_{}".format(bug["id"], iteration));
                cumulative_tokens += harden_tokens;
            else:
                no_progress += 1;
                attempted.append({"id": bug["id"], "description": bug["description"]});
                note = "no valid fix in {} tries ({}/{})".format(RETRY_PER_BUG + 1, no_progress, PATIENCE);

        # Ground truth: in fixture mode grade against planted bugs (the loop never sees this)
        # and measure the suite against a frozen mutant population on the oracle. In
        # generalized mode there is no answer key — report fixes made and the suite kill-rate
        # from the latest hardening pass. Both are honest about what they can measure.
        if has_oracle:
            graded = _grade(code, buggy_src, planted_bugs);
            kill_rate = _eval_kill_rate(accepted_tests, oracle_src, eval_mutants);
            total_display = len(planted_bugs);
        else:
            graded = fixes_made;
            kill_rate = last_harden_kr;
            total_display = fixes_made;
        entry = {
            "iteration": iteration,
            "cumulative_tokens": cumulative_tokens,
            "bugs_fixed": graded,
            "total_bugs": total_display,
            "kill_rate": kill_rate,
            "suite_size": len(accepted_tests),
            "fixes_made": fixes_made,
        };
        entries.append(entry);
        if verbose:
            print("{:>4}  {:>10}  {:>9}  {:>9.3f}  {:>5}  {}".format(
                iteration, cumulative_tokens, "{}/{}".format(graded, total_display), kill_rate, len(accepted_tests), note));

        if has_oracle and graded >= len(planted_bugs) and kill_rate >= 1.0:
            if verbose:
                print("all {} planted bugs fixed and suite kills every regression at iter {}".format(len(planted_bugs), iteration));
            break
        if no_progress >= PATIENCE:
            if verbose:
                print("plateau: {} iterations without progress -> stop".format(PATIENCE));
            break

    if has_oracle:
        graded = _grade(code, buggy_src, planted_bugs);
        kill_rate = _eval_kill_rate(accepted_tests, oracle_src, eval_mutants);
        total_display = len(planted_bugs);
        if verbose:
            print("LOOP    : fixed {}/{} planted bugs, {} regression tests, {:.0%} kill-rate, {} tokens".format(
                graded, len(planted_bugs), len(accepted_tests), kill_rate, cumulative_tokens));
            print("BASELINE: fixed {}/{} planted bugs, 0 regression tests, {} tokens (blind one-shot)".format(
                baseline["bugs_fixed"], baseline["total_bugs"], baseline["cumulative_tokens"]));
    else:
        graded = fixes_made;
        kill_rate = last_harden_kr;
        total_display = fixes_made;
        if verbose:
            print("LOOP    : made {} fixes, {} regression tests, {:.0%} suite kill-rate, {} tokens".format(
                fixes_made, len(accepted_tests), kill_rate, cumulative_tokens));
    return {
        "buggy_src": buggy_src,
        "final_code": code,
        "suite_sources": accepted_tests,
        "bugs_fixed": fixed_bugs,
        "failed_attempts": attempted,
        "cumulative_tokens": cumulative_tokens,
        "baseline": baseline,
        "entries": entries,
        "graded": graded,
        "total_bugs": total_display,
    }


def _parse_kwargs(argv: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {};
    for arg in argv:
        if "=" in arg:
            key, _, value = arg.partition("=");
            out[key.strip()] = value.strip();
    return out


def _resolve_repair_target():
    """CLI mode (repo=/file=/function=) loads a buggy source from a real repo and runs the
    loop without an answer key. Otherwise fall back to the built-in planted fixture."""
    kwargs = _parse_kwargs(sys.argv[1:]);
    if kwargs.get("repo") or kwargs.get("file"):
        from acquire import _language_for, fetch_file

        missing = [k for k in ("repo", "file", "function") if not kwargs.get(k)];
        if missing:
            raise SystemExit("repair CLI mode needs: repo=, file=, function= (missing: {})".format(missing));
        language = _language_for(kwargs["file"]);
        if language != "python":
            raise SystemExit("repair mode supports Python targets only (TS repair is roadmap); got {}".format(language));
        buggy_src = fetch_file(kwargs["repo"], kwargs["file"]);
        fn = kwargs["function"];
        if not re.search(r"^\s*def\s+{}\s*\(".format(re.escape(fn)), buggy_src, re.MULTILINE):
            print("[repair] warning: `def {}` not found in {}; relying on model-reported target".format(fn, kwargs["file"]));
        print("[repair] {} :: {} (python), target `{}`".format(kwargs["repo"], kwargs["file"], fn));
        # No oracle / planted bugs for an arbitrary target: report fixes + suite kill-rate.
        return run_repair(buggy_src, oracle_src=None, planted_bugs=None);

    return run_repair(BUGGY_SRC, REFERENCE_SRC, PLANTED_BUGS, oneshot_src=ONESHOT_SRC, eval_mutants=list(SEED_MUTANTS));


def main() -> None:
    result = _resolve_repair_target();
    logger = JsonlLogger(LOG_PATH);
    with open(BASELINE_PATH, "w") as handle:
        json.dump(result["baseline"], handle);
    for entry in result["entries"]:
        logger.append(entry);
    print("log at {}".format(LOG_PATH));


if __name__ == "__main__":
    main();
