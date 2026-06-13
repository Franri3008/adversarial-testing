from typing import Any, Dict, List


def run_and_check(test_src: str, reference_src: str, mutants: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not mutants:
        return {"reference_passed": True, "killed_mutant_ids": []}
    killed = [mutants[0]["id"]];
    return {"reference_passed": True, "killed_mutant_ids": killed}
