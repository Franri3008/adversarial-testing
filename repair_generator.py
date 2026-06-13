import ast
import re
from typing import Any, Dict, Optional

import llm


def _function_name(src: str) -> str:
    match = re.search(r"^\s*def\s+(\w+)\s*\(", src, re.MULTILINE);
    return match.group(1) if match else "subject"


def _build_bug_test_prompt(code: str, bug: Dict[str, Any], fn: str) -> str:
    return (
        "You are writing one pytest test that exposes a known bug for an automatic repair loop.\n"
        "The function under test is `{fn}` and is provided as a pytest FIXTURE, so your test "
        "MUST take `{fn}` as a parameter and call it (do not import or redefine it).\n"
        "Encode the CORRECT expected behavior, so the test FAILS on the current buggy code and "
        "PASSES once the bug is fixed.\n\n"
        "Bug: {bug}\n\n"
        "Current (buggy) source for context:\n"
        "```python\n{code}\n```\n\n"
        "Output ONLY the test code in a single ```python code block. No prose."
    ).format(fn=fn, bug=bug.get("description", ""), code=code)


def _extract_code(text: str) -> str:
    match = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL);
    return match.group(1).strip() if match else text.strip()


def _is_valid_fixture_test(test_src: str, fn: str) -> bool:
    try:
        tree = ast.parse(test_src);
    except SyntaxError:
        return False
    has_test = False;
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return False
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            arg_names = [arg.arg for arg in node.args.args];
            if fn in arg_names:
                has_test = True;
    return has_test


def generate_bug_test(code: str, bug: Dict[str, Any], stub_test_src: Optional[str] = None) -> Dict[str, Any]:
    fn = bug.get("target_name") or _function_name(code);
    prompt = _build_bug_test_prompt(code, bug, fn);
    response = llm.complete(prompt, role="bulk");
    text = response.get("text", "");
    if text.strip() == "STUB_COMPLETION":
        fallback = stub_test_src if stub_test_src else "";
        return {"test_src": fallback, "tokens": response["tokens"]}
    test_src = _extract_code(text);
    if not _is_valid_fixture_test(test_src, fn):
        test_src = stub_test_src if stub_test_src else test_src;
    return {"test_src": test_src, "tokens": response["tokens"]}
