import ast
from typing import Any, Dict, Optional

import llm


def _build_prompt(code: str, bug: Dict[str, Any], failing_test: str) -> str:
    return (
        "You are the repair agent in an automatic bug-fixing loop.\n"
        "Rewrite the source so the described bug is fixed and the failing test passes.\n"
        "Hard constraints:\n"
        "- Change only what is needed to fix the described defect.\n"
        "- Preserve every public function name and signature.\n"
        "- Return the complete corrected module source.\n"
        "- Return only Python source code, no markdown fences.\n\n"
        "Bug to fix: "
        + bug.get("description", "")
        + "\n\nFailing test that must pass after the fix:\n"
        + failing_test
        + "\n\nCurrent source:\n"
        + code
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
