import json
from typing import Any, Dict

import llm


def _build_prompt(observation: Dict[str, Any]) -> str:
    code = observation.get("code", "");
    fixed = observation.get("fixed_bug_descriptions", []);
    failed = observation.get("failed_attempts", []);
    fixed_text = "\n".join("- {}".format(item) for item in fixed) if fixed else "(none yet)";
    failed_text = "\n".join("- {}".format(item) for item in failed) if failed else "(none yet)";
    return (
        "You are the bug-finding strategist in an automatic repair loop.\n"
        "Inspect the current source and identify ONE concrete, real defect that is still present.\n"
        "Do not repeat any bug listed as already fixed or already attempted.\n"
        "If you are confident the code is correct, report that no bug remains.\n"
        "Return only valid JSON with this exact shape:\n"
        "{\"bug_found\":true,\"description\":\"what is wrong and the correct behavior\",\"target_name\":\"function name\",\"should_continue\":true}\n\n"
        "Already fixed:\n"
        + fixed_text
        + "\n\nAlready attempted without success:\n"
        + failed_text
        + "\n\nCurrent source:\n"
        + code
    )


def _next_seed(observation: Dict[str, Any]) -> Dict[str, Any]:
    seeds = observation.get("seed_bugs", []);
    fixed_ids = set(observation.get("fixed_bug_ids", []));
    failed_ids = set(observation.get("failed_attempt_ids", []));
    for seed in seeds:
        if seed.get("id") in fixed_ids or seed.get("id") in failed_ids:
            continue
        return seed
    return {}


def _fallback(observation: Dict[str, Any], tokens: Dict[str, int]) -> Dict[str, Any]:
    seed = _next_seed(observation);
    if not seed:
        return {"has_bug": False, "bug": {}, "should_continue": False, "tokens": tokens}
    bug = {"id": seed["id"], "description": seed["description"], "target_name": seed.get("target_name", "")};
    return {"has_bug": True, "bug": bug, "should_continue": True, "tokens": tokens}


def _load_json(text: str) -> Dict[str, Any]:
    stripped = text.strip();
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{");
        end = stripped.rfind("}");
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            return json.loads(stripped[start:end + 1])
        except json.JSONDecodeError:
            return {}


def _parse_decision(text: str, observation: Dict[str, Any], tokens: Dict[str, int]) -> Dict[str, Any]:
    parsed = _load_json(text);
    if not parsed:
        return _fallback(observation, tokens)
    bug_found = parsed.get("bug_found", False);
    should_continue = parsed.get("should_continue", bool(bug_found));
    if not isinstance(should_continue, bool):
        should_continue = bool(bug_found);
    description = parsed.get("description", "");
    target_name = parsed.get("target_name", "");
    if not bug_found or not isinstance(description, str) or not description.strip():
        return {"has_bug": False, "bug": {}, "should_continue": should_continue, "tokens": tokens}
    bug_id = "bug_{}".format(observation.get("next_bug_index", 1));
    bug = {"id": bug_id, "description": description.strip(), "target_name": target_name if isinstance(target_name, str) else ""};
    return {"has_bug": True, "bug": bug, "should_continue": True, "tokens": tokens}


def find_bug(observation: Dict[str, Any]) -> Dict[str, Any]:
    prompt = _build_prompt(observation);
    response = llm.complete(prompt, role="strategy");
    tokens = response.get("tokens", {"in": 0, "out": 0});
    text = response.get("text", "");
    if text.strip() == "STUB_COMPLETION":
        return _fallback(observation, tokens)
    return _parse_decision(text, observation, tokens)
