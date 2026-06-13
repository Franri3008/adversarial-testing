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
        "You are the DEFENDER in a mutation-testing loop: you write tests that catch bugs.\n"
        "Write ONE pytest test function for `{fn}` whose assertions PASS on the correct\n"
        "implementation but FAIL on any implementation carrying one of the target bugs listed\n"
        "at the end of this prompt.\n\n"
        "Rules (hard requirements):\n"
        "- `{fn}` is supplied as a pytest FIXTURE. Your test MUST take `{fn}` as a parameter\n"
        "  and call it. NEVER import or redefine it.\n"
        "- Every assertion MUST pass on the correct reference. A test that fails on the\n"
        "  reference is wasted — the loop discards it as a false alarm.\n"
        "- Assert concrete expected outputs you work out from the intended behavior; do NOT\n"
        "  paste the reference implementation into the test. Target the specific bugs: pick\n"
        "  inputs that exercise the edge cases they describe (boundaries, empty/invalid input,\n"
        "  error paths), not just the happy path.\n\n"
        "<reference language=\"python\">\n{ref}\n</reference>"
    ).format(fn=fn, ref=reference_src)
    suffix = (
        "\n\n<target_bugs>\n{clues}\n</target_bugs>\n\n"
        "Output ONLY the test code in a single ```python code block. No prose."
    ).format(clues=_clues(surviving))
    return prefix, suffix


def _prompt_typescript(
    reference_src: str,
    fn: str,
    surviving: List[Dict[str, Any]],
    import_path: str = "./impl",
):
    prefix = (
        "You are the DEFENDER in a mutation-testing loop: you write tests that catch bugs.\n"
        "Write ONE vitest test (TypeScript) for `{fn}` whose assertions PASS on the correct\n"
        "implementation but FAIL on any implementation carrying one of the target bugs listed\n"
        "at the end of this prompt.\n\n"
        "Rules (hard requirements):\n"
        "- Import the function with `import {{ {fn} }} from \"{import_path}\";` and import\n"
        "  `test` and `expect` from \"vitest\". NEVER redefine the function.\n"
        "- Every assertion MUST pass on the correct reference. A test that fails on the\n"
        "  reference is wasted — the loop discards it as a false alarm.\n"
        "- For inputs that must be rejected, assert it throws: "
        "`expect(() => {fn}(x)).toThrow();`\n"
        "- Assert concrete expected outputs you work out from the intended behavior; do NOT\n"
        "  paste the reference implementation in. Target the specific bugs (boundaries,\n"
        "  empty/invalid input, error paths), not just the happy path.\n\n"
        "<reference language=\"typescript\">\n{ref}\n</reference>"
    ).format(fn=fn, import_path=import_path, ref=reference_src)
    suffix = (
        "\n\n<target_bugs>\n{clues}\n</target_bugs>\n\n"
        "Output ONLY the test code in a single ```typescript code block. No prose."
    ).format(clues=_clues(surviving))
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
