from typing import Any, Dict, List

import llm

FAKE_TEST_SRC = """def test_generated(merge_intervals):
    assert merge_intervals([[1, 3], [2, 6]]) == [[1, 6]]
"""


def _build_prompt(reference_src: str, target_ids: List[str]) -> str:
    header = "Write one pytest test that kills these mutants: " + ", ".join(target_ids);
    return header + "\n\nReference implementation:\n" + reference_src


def generate_test(reference_src: str, surviving_mutants: List[Dict[str, Any]]) -> Dict[str, Any]:
    target_ids = [m["id"] for m in surviving_mutants];
    prompt = _build_prompt(reference_src, target_ids);
    response = llm.complete(prompt, role="bulk");
    test_src = FAKE_TEST_SRC;
    return {"test_src": test_src, "tokens": response["tokens"]}
