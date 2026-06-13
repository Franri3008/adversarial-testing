import re
from typing import Any, Dict, List

import llm


def _function_name(reference_src: str) -> str:
    m = re.search(r"^\s*def\s+(\w+)\s*\(", reference_src, re.MULTILINE)
    return m.group(1) if m else "subject"


def _build_prompt(reference_src: str, fn: str, surviving: List[Dict[str, Any]]) -> str:
    # Hand the model the BEHAVIORS the surviving mutants get wrong (not just ids),
    # so it writes assertions that actually distinguish correct from buggy.
    clues = "\n".join("- {}: {}".format(m["id"], m.get("description", "")) for m in surviving)
    return (
        "You are writing an adversarial pytest test for mutation testing.\n"
        "The function under test is `{fn}` and is provided as a pytest FIXTURE, so your "
        "test MUST take `{fn}` as a parameter and call it (do not import or redefine it).\n\n"
        "Write ONE test function with several assertions that PASS on the correct "
        "implementation but would FAIL on implementations exhibiting these bugs:\n"
        "{clues}\n\n"
        "Correct reference implementation (for behavior, do not copy into the test):\n"
        "```python\n{ref}\n```\n\n"
        "Output ONLY the test code in a single ```python code block. No prose."
    ).format(fn=fn, clues=clues, ref=reference_src)


def _extract_code(text: str, fn: str) -> str:
    # Prefer a fenced ```python block; fall back to any ``` block; then raw text.
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
    code = m.group(1).strip() if m else text.strip()
    return code


def generate_test(
    reference_src: str,
    surviving_mutants: List[Dict[str, Any]],
    role: str = "bulk",
) -> Dict[str, Any]:
    fn = _function_name(reference_src)
    prompt = _build_prompt(reference_src, fn, surviving_mutants)
    response = llm.complete(prompt, role=role)
    test_src = _extract_code(response["text"], fn)
    return {
        "test_src": test_src,
        "tokens": response["tokens"],
        "model": response.get("model", role),
        "cost": response.get("cost", 0.0),
        "role": role,
    }
