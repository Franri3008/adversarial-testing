import ast
from typing import Any, Dict, Optional

import llm


def _build_prompt(code: str, bug: Dict[str, Any], failing_test: str) -> str:
    return (
        "You are the repair agent in an automatic bug-fixing loop. Rewrite the module so the\n"
        "described bug is fixed and the failing test passes.\n\n"
        "Hard requirements:\n"
        "- Fix ONLY the described defect, with the smallest change that does so. Do not\n"
        "  refactor, rename, reformat, or alter any behavior unrelated to the bug.\n"
        "- Preserve every public function name and signature exactly.\n"
        "- Do NOT modify the test. The fix must make the given test pass as written.\n"
        "- Return the COMPLETE corrected module source. Python only — no markdown fences,\n"
        "  no prose.\n\n"
        "<bug>\n" + bug.get("description", "") + "\n</bug>\n\n"
        "<failing_test>\n" + failing_test + "\n</failing_test>\n\n"
        "<source>\n" + code + "\n</source>"
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


def _is_valid_module(src: str) -> bool:
    try:
        ast.parse(src);
    except SyntaxError:
        return False
    return True


def generate_fix(code: str, bug: Dict[str, Any], failing_test: str, oracle_src: Optional[str] = None, stub_fixed_src: Optional[str] = None) -> Dict[str, Any]:
    prompt = _build_prompt(code, bug, failing_test);
    response = llm.complete(prompt, role="strategy");
    tokens = response.get("tokens", {"in": 0, "out": 0});
    text = response.get("text", "");
    if text.strip() == "STUB_COMPLETION":
        fixed_src = stub_fixed_src or oracle_src or code;
        return {"fixed_src": fixed_src, "tokens": tokens}
    fixed_src = _extract_code(text);
    if not _is_valid_module(fixed_src):
        fixed_src = stub_fixed_src or oracle_src or code;
    return {"fixed_src": fixed_src, "tokens": tokens}
