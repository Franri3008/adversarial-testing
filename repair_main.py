import ast
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1");

from fixer import generate_fix
from fixtures.buggy import BUGGY_SRC, MUTANTS as SEED_MUTANTS, PLANTED_BUGS, REFERENCE_SRC
from generator import generate_test
from harness import JsonlLogger, compute_kill_rate
import llm
from repair_generator import generate_bug_test
import runner
from strategy import find_bug

MAX_ITERATIONS = 12;
HARDEN_ATTEMPTS = 3;
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
    if "def grade" in code:
        return list(SEED_MUTANTS)
    return []


def _discover_mutants(code: str) -> List[Dict[str, Any]]:
    response = llm.complete(_build_discovery_prompt(code), role="strategy");
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


def _oneshot_baseline(buggy_src: str, oracle_src: str, planted_bugs: List[Dict[str, Any]]) -> Dict[str, Any]:
    combined = {"description": "Fix every defect so the function behaves correctly.", "target_name": _function_name(buggy_src)};
    suite = _suite_text([_mangle(bug["stub_test_src"], bug["id"]) for bug in planted_bugs]);
    fix = generate_fix(buggy_src, combined, suite, oracle_src=oracle_src, stub_fixed_src=oracle_src);
    fixed_src = fix["fixed_src"];
    tokens = _token_count(fix["tokens"]);
    fixed_count = _grade(fixed_src, buggy_src, planted_bugs);
    return {"bugs_fixed": fixed_count, "total_bugs": len(planted_bugs), "cumulative_tokens": tokens}


def main() -> None:
    code = BUGGY_SRC;
    buggy_src = code;
    oracle_src = REFERENCE_SRC;
    seed_bugs = [{"id": bug["id"], "description": bug["description"], "target_name": bug["target_name"]} for bug in PLANTED_BUGS];
    stub_tests = {bug["id"]: bug["stub_test_src"] for bug in PLANTED_BUGS};
    stub_fixes = {bug["id"]: bug["stub_fixed_src"] for bug in PLANTED_BUGS};

    logger = JsonlLogger(LOG_PATH);
    baseline = _oneshot_baseline(buggy_src, oracle_src, PLANTED_BUGS);
    with open(BASELINE_PATH, "w") as handle:
        json.dump(baseline, handle);
    print("one-shot baseline: fixed {}/{} bugs, tokens {}".format(baseline["bugs_fixed"], baseline["total_bugs"], baseline["cumulative_tokens"]));

    suite_sources = [];
    bugs_fixed = [];
    failed_attempts = [];
    cumulative_tokens = baseline["cumulative_tokens"];

    print("iteration  cumulative_tokens  bugs_fixed  kill_rate  fixed_this_round");
    for iteration in range(1, MAX_ITERATIONS + 1):
        observation = _build_observation(code, bugs_fixed, failed_attempts, seed_bugs, cumulative_tokens);
        decision = find_bug(observation);
        cumulative_tokens += _token_count(decision["tokens"]);
        if not decision["should_continue"] or not decision["has_bug"]:
            print("no further bugs reported at iteration {}".format(iteration));
            break

        bug = decision["bug"];
        gen = generate_bug_test(code, bug, stub_test_src=stub_tests.get(bug["id"]));
        cumulative_tokens += _token_count(gen["tokens"]);
        test_src = gen["test_src"];

        fix = generate_fix(code, bug, test_src, oracle_src=oracle_src, stub_fixed_src=stub_fixes.get(bug["id"]));
        cumulative_tokens += _token_count(fix["tokens"]);
        fixed_src = fix["fixed_src"];

        if not _verify_fix(test_src, fixed_src, code, bug["id"], bug["description"]):
            failed_attempts.append({"id": bug["id"], "description": bug["description"]});
            print("{:>9}  {:>17}  {:>10}  {:>9}  {}".format(iteration, cumulative_tokens, len(bugs_fixed), "-", "rejected:" + bug["id"]));
            continue

        code = fixed_src;
        suite_sources.append(_mangle(test_src, bug["id"]));
        bugs_fixed.append(bug);

        mutants = _discover_mutants(code);
        kill_rate, surviving, harden_tokens = _harden(code, suite_sources, mutants, bug["id"]);
        cumulative_tokens += harden_tokens;

        entry = {
            "iteration": iteration,
            "cumulative_tokens": cumulative_tokens,
            "bugs_fixed": len(bugs_fixed),
            "kill_rate": kill_rate,
            "fixed_this_round": bug["id"],
        };
        logger.append(entry);
        print("{:>9}  {:>17}  {:>10}  {:>9.3f}  {}".format(iteration, cumulative_tokens, len(bugs_fixed), kill_rate, bug["id"]));

    graded = _grade(code, buggy_src, PLANTED_BUGS);
    print("loop fixed {}/{} planted bugs (graded), {} tests in suite, log at {}".format(graded, len(PLANTED_BUGS), len(suite_sources), LOG_PATH));


if __name__ == "__main__":
    main();
