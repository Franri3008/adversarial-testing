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
        "You are the bug-finding strategist in an automatic repair loop. Inspect the source\n"
        "and identify ONE concrete, still-present defect: a case where the code returns the\n"
        "wrong result, crashes, or mishandles an input it is meant to handle. Only behavior\n"
        "bugs count — ignore style, naming, and performance.\n\n"
        "Do not repeat anything listed below as already fixed or already attempted.\n"
        "If you are confident no real defect remains, report that instead of inventing one.\n\n"
        "Return ONLY valid JSON, no prose, in exactly one of these two shapes:\n"
        "  {\"bug_found\":true,\"description\":\"what is wrong AND the correct behavior\",\"target_name\":\"function name\",\"should_continue\":true}\n"
        "  {\"bug_found\":false,\"description\":\"\",\"target_name\":\"\",\"should_continue\":false}\n"
        "`should_continue` means: is it worth looking for further bugs after this one?\n\n"
        "<already_fixed>\n"
        + fixed_text
        + "\n</already_fixed>\n\n<already_attempted>\n"
        + failed_text
        + "\n</already_attempted>\n\n<source>\n"
        + code
        + "\n</source>"
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
    # Carry the seed's offline test/fix so the stub-backed demo can run without a model.
    for key in ("stub_test_src", "stub_fixed_src"):
        if seed.get(key):
            bug[key] = seed[key];
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
