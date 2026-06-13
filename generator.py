import ast
from typing import Any, Dict, List, Optional

import llm

def _target_name(reference_src: str) -> str:
    try:
        tree = ast.parse(reference_src);
    except SyntaxError:
        return "target"
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node.name
    return "target"


def _noop_test(target_name: str) -> str:
    return "def test_placeholder():\n    assert {0} is {0}\n".format(target_name)


def _build_prompt(reference_src: str, surviving_mutants: List[Dict[str, Any]], target_ids: List[str], hint: str, target_name: str) -> str:
    mutant_lines = [];
    for mutant in surviving_mutants:
        if mutant["id"] in target_ids:
            mutant_lines.append("- {}: {}".format(mutant["id"], mutant["description"]));
    target_text = ", ".join(target_ids) if target_ids else "all surviving mutants";
    hint_text = hint if hint else "Focus on small, decisive edge cases that distinguish the reference from targeted mutants.";
    return (
        "Write one pytest-compatible test module for the function {}.\n".format(target_name)
        + "Hard constraints:\n"
        + "- Do not import the target or any fixture.\n"
        + "- Reference {} as an existing global name.\n".format(target_name)
        + "- Define one or more def test_*() functions.\n"
        + "- Test functions must take no arguments.\n"
        + "- Use plain assert statements.\n"
        + "- Return only Python source code, no markdown fences.\n\n"
        + "Target mutant IDs: "
        + target_text
        + "\nStrategist hint: "
        + hint_text
        + "\nTargeted mutant descriptions:\n"
        + "\n".join(mutant_lines)
        + "\n\nReference implementation:\n"
        + reference_src
    )


def _extract_code(text: str) -> str:
    stripped = text.strip();
    if stripped.startswith("```"):
        lines = stripped.splitlines();
        if lines and lines[0].startswith("```"):
            lines = lines[1:];
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1];
        stripped = "\n".join(lines).strip();
    return stripped


def _is_valid_test_src(test_src: str, target_name: str) -> bool:
    try:
        tree = ast.parse(test_src);
    except SyntaxError:
        return False
    has_test = False;
    has_target_reference = target_name in test_src;
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return False
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            has_test = True;
            if node.args.args or node.args.vararg or node.args.kwonlyargs or node.args.kwarg:
                return False
    if not has_test:
        return False
    if not has_target_reference:
        return False
    return True


def _build_bug_test_prompt(code: str, bug: Dict[str, Any], target_name: str) -> str:
    return (
        "Write one pytest-compatible test that exposes the described bug in the function {}.\n".format(target_name)
        + "The test must encode the CORRECT expected behavior, so it fails on the current buggy code and passes once the bug is fixed.\n"
        + "Hard constraints:\n"
        + "- Do not import the target or any fixture.\n"
        + "- Reference {} as an existing global name.\n".format(target_name)
        + "- Define one or more def test_*() functions taking no arguments.\n"
        + "- Use plain assert statements.\n"
        + "- Return only Python source code, no markdown fences.\n\n"
        + "Bug: "
        + bug.get("description", "")
        + "\n\nCurrent source:\n"
        + code
    )


def generate_test(reference_src: str, surviving_mutants: List[Dict[str, Any]], target_ids: Optional[List[str]] = None, hint: str = "", target_name: Optional[str] = None) -> Dict[str, Any]:
    if target_ids is None:
        target_ids = [m["id"] for m in surviving_mutants];
    if target_name is None:
        target_name = _target_name(reference_src);
    prompt = _build_prompt(reference_src, surviving_mutants, target_ids, hint, target_name);
    response = llm.complete(prompt, role="bulk");
    text = response.get("text", "");
    if text.strip() == "STUB_COMPLETION":
        return {"test_src": _noop_test(target_name), "tokens": response["tokens"]}
    test_src = _extract_code(text);
    if not _is_valid_test_src(test_src, target_name):
        test_src = _noop_test(target_name);
    return {"test_src": test_src, "tokens": response["tokens"]}


def generate_bug_test(code: str, bug: Dict[str, Any], stub_test_src: Optional[str] = None) -> Dict[str, Any]:
    target_name = bug.get("target_name") or _target_name(code);
    prompt = _build_bug_test_prompt(code, bug, target_name);
    response = llm.complete(prompt, role="bulk");
    text = response.get("text", "");
    if text.strip() == "STUB_COMPLETION":
        fallback = stub_test_src if stub_test_src else _noop_test(target_name);
        return {"test_src": fallback, "tokens": response["tokens"]}
    test_src = _extract_code(text);
    if not _is_valid_test_src(test_src, target_name):
        test_src = stub_test_src if stub_test_src else _noop_test(target_name);
    return {"test_src": test_src, "tokens": response["tokens"]}
