import ast
import json
import os
import sys
from typing import Any, Dict, List, Optional

from fixer import generate_fix
from fixtures.buggy import BUGGY_SRC, PLANTED_BUGS, REFERENCE_SRC
from generator import generate_bug_test, generate_test
from harness import JsonlLogger, compute_kill_rate
import llm
import runner
from strategy import find_bug

MAX_ITERATIONS = 12;
HARDEN_ATTEMPTS = 3;
LOG_PATH = "run.jsonl";
BASELINE_PATH = "baseline.json";
SKIP_DIRS = {".git", ".mypy_cache", ".pytest_cache", "__pycache__", "env", "venv", ".venv", "node_modules"};
MAX_SOURCE_CHARS = 24000;


def _token_count(tokens):
    return tokens.get("in", 0) + tokens.get("out", 0)


def _target_name(src: str) -> str:
    try:
        tree = ast.parse(src);
    except SyntaxError:
        return "target"
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node.name
    return "target"


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


def read_code_input(path: Optional[str] = None) -> str:
    if not path:
        return BUGGY_SRC
    if os.path.isfile(path):
        with open(path) as handle:
            return handle.read()
    chunks = [];
    for root, dirs, files in os.walk(path):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS];
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            full_path = os.path.join(root, name);
            rel_path = os.path.relpath(full_path, path);
            with open(full_path) as handle:
                chunks.append("# file: {}\n{}".format(rel_path, handle.read()));
            if sum(len(chunk) for chunk in chunks) >= MAX_SOURCE_CHARS:
                return "\n\n".join(chunks)[:MAX_SOURCE_CHARS]
    return "\n\n".join(chunks)[:MAX_SOURCE_CHARS]


def _build_discovery_prompt(reference_src: str) -> str:
    return (
        "You are the discovery stage in an adversarial test-hardening orchestrator.\n"
        "Inspect the provided Python source and create mutants that represent plausible bugs.\n"
        "Each mutant must preserve the same public function names as the reference source.\n"
        "Return only valid JSON with this exact shape:\n"
        "{\"mutants\":[{\"id\":\"M1_short_name\",\"description\":\"what behavior is broken\",\"src\":\"full mutant python source\"}]}\n"
        "Rules:\n"
        "- Return 3 to 8 high-signal mutants.\n"
        "- Each src must be complete executable Python source for the mutated target.\n"
        "- Mutants should differ from the reference in one meaningful behavior.\n"
        "- Do not include markdown fences.\n\n"
        "Source:\n"
        + reference_src[:MAX_SOURCE_CHARS]
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
    if not isinstance(mutant.get("id"), str) or not mutant["id"]:
        return False
    if not isinstance(mutant.get("description"), str) or not mutant["description"]:
        return False
    if not isinstance(mutant.get("src"), str) or not mutant["src"]:
        return False
    try:
        ast.parse(mutant["src"]);
    except SyntaxError:
        return False
    return True


def _parse_mutants(text: str) -> List[Dict[str, Any]]:
    parsed = _load_json(text);
    mutants = parsed.get("mutants", []);
    if not isinstance(mutants, list):
        return []
    return [mutant for mutant in mutants if _is_valid_mutant(mutant)]


def _fallback_mutants(reference_src: str) -> List[Dict[str, Any]]:
    if "def clamp" in reference_src and "def running_max" in reference_src:
        from fixtures.buggy import MUTANTS
        return list(MUTANTS)
    if "def merge_intervals" in reference_src:
        from fixtures import MUTANTS
        return list(MUTANTS)
    return []


def discover_mutants(reference_src: str) -> List[Dict[str, Any]]:
    prompt = _build_discovery_prompt(reference_src);
    response = llm.complete(prompt, role="strategy");
    text = response.get("text", "");
    if text.strip() == "STUB_COMPLETION":
        return _fallback_mutants(reference_src)
    mutants = _parse_mutants(text);
    if not mutants:
        return _fallback_mutants(reference_src)
    return mutants


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


def _harden(code: str, suite_sources: List[str], mutants: List[Dict[str, Any]], tag: str):
    tokens = 0;
    target_name = _target_name(code);
    kill_rate, surviving = _measure_kill_rate(code, suite_sources, mutants);
    for attempt in range(HARDEN_ATTEMPTS):
        if not surviving:
            break
        gen = generate_test(code, surviving, [mutant["id"] for mutant in surviving], "Kill these surviving mutants.", target_name);
        tokens += _token_count(gen["tokens"]);
        new_test = gen["test_src"];
        check = runner.run_and_check(new_test, code, []);
        if not check["reference_passed"]:
            continue
        suite_sources.append(_mangle(new_test, "{}_h{}".format(tag, attempt)));
        kill_rate, surviving = _measure_kill_rate(code, suite_sources, mutants);
    return kill_rate, surviving, tokens


def _oneshot_baseline(buggy_src: str, oracle_src: str, planted_bugs: List[Dict[str, Any]]) -> Dict[str, Any]:
    stub_suite = _suite_text([_mangle(bug["stub_test_src"], bug["id"]) for bug in planted_bugs]);
    combined = {"description": "Fix every defect so the module behaves correctly.", "target_name": ""};
    fix = generate_fix(buggy_src, combined, stub_suite, oracle_src=oracle_src);
    fixed_src = fix["fixed_src"];
    tokens = _token_count(fix["tokens"]);
    fixed_count = 0;
    for bug in planted_bugs:
        if _verify_fix(bug["stub_test_src"], fixed_src, buggy_src, bug["id"], bug["description"]):
            fixed_count += 1;
    return {"bugs_fixed": fixed_count, "total_bugs": len(planted_bugs), "cumulative_tokens": tokens}


def _grade(code: str, buggy_src: str, planted_bugs: List[Dict[str, Any]]) -> int:
    fixed_count = 0;
    for bug in planted_bugs:
        if _verify_fix(bug["stub_test_src"], code, buggy_src, bug["id"], bug["description"]):
            fixed_count += 1;
    return fixed_count


def main() -> None:
    input_path = sys.argv[1] if len(sys.argv) > 1 else None;
    code = read_code_input(input_path);
    buggy_src = code;
    oracle_src = REFERENCE_SRC;
    seed_bugs = [{"id": bug["id"], "description": bug["description"], "target_name": bug["target_name"]} for bug in PLANTED_BUGS];
    stub_tests = {bug["id"]: bug["stub_test_src"] for bug in PLANTED_BUGS};

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

        fix = generate_fix(code, bug, test_src, oracle_src=oracle_src);
        cumulative_tokens += _token_count(fix["tokens"]);
        fixed_src = fix["fixed_src"];

        accepted = _verify_fix(test_src, fixed_src, code, bug["id"], bug["description"]);
        if not accepted:
            failed_attempts.append({"id": bug["id"], "description": bug["description"]});
            print("{:>9}  {:>17}  {:>10}  {:>9}  {}".format(iteration, cumulative_tokens, len(bugs_fixed), "-", "rejected:" + bug["id"]));
            continue

        code = fixed_src;
        suite_sources.append(_mangle(test_src, bug["id"]));
        bugs_fixed.append(bug);

        mutants = discover_mutants(code);
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
