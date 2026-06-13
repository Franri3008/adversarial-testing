import ast
import re
from typing import Any, Dict, Optional

import llm


def _function_name(src: str) -> str:
    match = re.search(r"^\s*def\s+(\w+)\s*\(", src, re.MULTILINE);
    return match.group(1) if match else "subject"


def _build_bug_test_prompt(code: str, bug: Dict[str, Any], fn: str) -> str:
    return (
        "You are writing ONE pytest test that pins down the CORRECT behavior a known bug\n"
        "violates, for an automatic repair loop.\n\n"
        "Rules (hard requirements):\n"
        "- `{fn}` is supplied as a pytest FIXTURE. Your test MUST take `{fn}` as a parameter\n"
        "  and call it. NEVER import or redefine it.\n"
        "- Assert the CORRECT expected behavior, NEVER the current buggy behavior. The test\n"
        "  must FAIL on the buggy source below and PASS once the bug is fixed.\n"
        "- Choose inputs that actually trigger the bug.\n\n"
        "<bug>\n{bug}\n</bug>\n\n"
        "<buggy_source language=\"python\">\n{code}\n</buggy_source>\n\n"
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


def generate_bug_test(code: str, bug: Dict[str, Any], stub_test_src: Optional[str] = None, role: str = "bulk") -> Dict[str, Any]:
    fn = bug.get("target_name") or _function_name(code);
    prompt = _build_bug_test_prompt(code, bug, fn);
    response = llm.complete(prompt, role=role);
    text = response.get("text", "");
    if text.strip() == "STUB_COMPLETION":
        fallback = stub_test_src if stub_test_src else "";
        return {"test_src": fallback, "tokens": response["tokens"]}
    test_src = _extract_code(text);
    if not _is_valid_fixture_test(test_src, fn):
        test_src = stub_test_src if stub_test_src else test_src;
    return {"test_src": test_src, "tokens": response["tokens"]}
