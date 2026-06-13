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


# Prompt structure for caching: the stable parts (instructions + reference src) go
# into `prefix`, which is sent as a cache_control block. Only `suffix` (the surviving
# mutant clues) changes between iterations, so iterations 2..N get a cache hit.
def _prompt_python(reference_src: str, fn: str, surviving: List[Dict[str, Any]]):
    prefix = (
        "You are writing an adversarial pytest test for mutation testing.\n"
        "The function under test is `{fn}` and is provided as a pytest FIXTURE, so your "
        "test MUST take `{fn}` as a parameter and call it (do not import or redefine it).\n\n"
        "Correct reference implementation (for behavior, do not copy into the test):\n"
        "```python\n{ref}\n```\n\n"
        "Write ONE test function with several assertions that PASS on the correct "
        "implementation but would FAIL on implementations exhibiting the bugs listed below.\n"
        "Output ONLY the test code in a single ```python code block. No prose."
    ).format(fn=fn, ref=reference_src)
    suffix = "Surviving bugs to target:\n{clues}".format(clues=_clues(surviving))
    return prefix, suffix


def _prompt_typescript(
    reference_src: str,
    fn: str,
    surviving: List[Dict[str, Any]],
    import_path: str = "./impl",
):
    prefix = (
        "You are writing an adversarial vitest test (TypeScript) for mutation testing.\n"
        "Import the function under test with `import {{ {fn} }} from \"{import_path}\";` and import "
        "`test` and `expect` from \"vitest\". Do not redefine the function.\n\n"
        "Correct reference implementation (for behavior, do not copy into the test):\n"
        "```typescript\n{ref}\n```\n\n"
        "Write ONE test with several assertions that PASS on the correct implementation but "
        "would FAIL on implementations exhibiting the bugs listed below.\n"
        "For inputs that must be rejected, assert it throws: "
        "`expect(() => {fn}(x)).toThrow();`\n\n"
        "Output ONLY the test code in a single ```typescript code block. No prose."
    ).format(fn=fn, import_path=import_path, ref=reference_src)
    suffix = "Surviving bugs to target:\n{clues}".format(clues=_clues(surviving))
    return prefix, suffix


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
    test_import_path: Optional[str] = None,
) -> Dict[str, Any]:
    if language == "typescript":
        fn = _ts_function_name(reference_src, function_name)
        prefix, suffix = _prompt_typescript(
            reference_src, fn, surviving_mutants, test_import_path or "./impl"
        )
    else:
        fn = function_name or _python_function_name(reference_src)
        prefix, suffix = _prompt_python(reference_src, fn, surviving_mutants)

    response = llm.complete(suffix, role=role, cache_prefix=prefix)
    test_src = _extract_code(response["text"])
    return {
        "test_src": test_src,
        "tokens": response["tokens"],
        "model": response.get("model", role),
        "cost": response.get("cost", 0.0),
        "role": role,
    }
