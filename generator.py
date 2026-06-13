import re
from typing import Any, Dict, List, Optional

import llm


def _python_function_name(reference_src: str) -> str:
    m = re.search(r"^\s*def\s+(\w+)\s*\(", reference_src, re.MULTILINE)
    return m.group(1) if m else "subject"


def _ts_function_name(reference_src: str, given: Optional[str]) -> str:
    if given:
        return given
    m = re.search(r"export\s+function\s+(\w+)\s*\(", reference_src)
    return m.group(1) if m else "subject"


def _clues(surviving: List[Dict[str, Any]]) -> str:
    return "\n".join("- {}: {}".format(m["id"], m.get("description", "")) for m in surviving)


def _build_prompt_python(reference_src: str, fn: str, surviving: List[Dict[str, Any]]) -> str:
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
    ).format(fn=fn, clues=_clues(surviving), ref=reference_src)


def _build_prompt_typescript(reference_src: str, fn: str, surviving: List[Dict[str, Any]]) -> str:
    return (
        "You are writing an adversarial vitest test (TypeScript) for mutation testing.\n"
        "Import the function under test with `import {{ {fn} }} from \"./impl\";` and import "
        "`test` and `expect` from \"vitest\". Do not redefine the function.\n\n"
        "Write ONE test with several assertions that PASS on the correct implementation but "
        "would FAIL on implementations exhibiting these bugs:\n"
        "{clues}\n\n"
        "For inputs that must be rejected, assert it throws: "
        "`expect(() => {fn}(x)).toThrow();`\n\n"
        "Correct reference implementation (for behavior, do not copy into the test):\n"
        "```typescript\n{ref}\n```\n\n"
        "Output ONLY the test code in a single ```typescript code block. No prose."
    ).format(fn=fn, clues=_clues(surviving), ref=reference_src)


def _extract_code(text: str) -> str:
    # Prefer a fenced code block (python/ts/typescript/js); fall back to raw text.
    m = re.search(r"```(?:[a-zA-Z]+)?\s*(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def generate_test(
    reference_src: str,
    surviving_mutants: List[Dict[str, Any]],
    role: str = "bulk",
    language: str = "python",
    function_name: Optional[str] = None,
) -> Dict[str, Any]:
    if language == "typescript":
        fn = _ts_function_name(reference_src, function_name)
        prompt = _build_prompt_typescript(reference_src, fn, surviving_mutants)
    else:
        fn = function_name or _python_function_name(reference_src)
        prompt = _build_prompt_python(reference_src, fn, surviving_mutants)

    response = llm.complete(prompt, role=role)
    test_src = _extract_code(response["text"])
    return {
        "test_src": test_src,
        "tokens": response["tokens"],
        "model": response.get("model", role),
        "cost": response.get("cost", 0.0),
        "role": role,
    }
