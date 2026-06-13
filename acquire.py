"""Acquire a mutation-testing target from a real repo, no fixture authoring.

Given a repo URL + file path + function name, this:
  1. fetches just that file via `gh api` (no clone),
  2. uses the file as the reference implementation,
  3. asks the strategy model to generate N realistic single-bug mutants,
  4. validates them — drops duplicates, no-ops, and anything that does not compile
     (via the language's runner.compiles), so a broken mutant can never be a false kill.

Returns a fixture-shaped target the existing loop already understands.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import llm

EXT_LANGUAGE = {".ts": "typescript", ".tsx": "typescript", ".py": "python"}


@dataclass
class Target:
    reference_src: str
    mutants: List[Dict[str, Any]]
    language: str
    function_name: str


def _parse_repo(url: str) -> str:
    """https://github.com/OWNER/NAME(.git) -> 'OWNER/NAME'."""
    m = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    if not m:
        # Allow a bare "owner/name" too.
        if re.fullmatch(r"[^/\s]+/[^/\s]+", url.strip()):
            return url.strip()
        raise ValueError(f"Could not parse owner/name from repo='{url}'")
    return f"{m.group(1)}/{m.group(2)}"


def _language_for(path: str) -> str:
    for ext, lang in EXT_LANGUAGE.items():
        if path.endswith(ext):
            return lang
    raise ValueError(f"Unsupported file type for '{path}' (supported: {sorted(EXT_LANGUAGE)})")


def fetch_file(repo_url: str, path: str) -> str:
    repo = _parse_repo(repo_url)
    proc = subprocess.run(
        ["gh", "api", f"repos/{repo}/contents/{path}", "--jq", ".content"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh api failed for {repo}/{path}: {proc.stderr.strip()[:200]}")
    import base64

    return base64.b64decode(proc.stdout.strip()).decode("utf-8")


_MUTANT_PROMPT = """\
You are generating mutants for mutation testing. Below is a CORRECT {language}
implementation. The function under test is `{fn}`.

Produce {n} DISTINCT mutants. Each mutant is a FULL copy of the code with exactly ONE
small, realistic bug introduced into `{fn}` — e.g. an off-by-one, a flipped comparison,
a wrong constant/default, a dropped guard/validation, a wrong operator. Each mutant MUST
still compile/parse and keep the same function signature and exports.

Return ONLY a JSON array, no prose:
[{{"id": "<short_snake_case_id>", "description": "<one line: what bug>", "src": "<full module source>"}}]

Correct implementation:
```{language}
{ref}
```
"""


def _extract_json_array(text: str) -> List[dict]:
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON array in mutant output: {text[:200]!r}")
    return json.loads(m.group(0))


def _compiles_fn(language: str):
    if language == "typescript":
        from runner_ts import compiles
    else:
        from runner import compiles
    return compiles


def generate_mutants(
    reference_src: str, function_name: str, language: str, n: int
) -> List[Dict[str, Any]]:
    prompt = _MUTANT_PROMPT.format(language=language, fn=function_name, n=n, ref=reference_src)
    response = llm.complete(prompt, role="strategy")
    candidates = _extract_json_array(response["text"])

    compiles = _compiles_fn(language)
    ref_norm = reference_src.strip()
    seen_src: set[str] = set()
    valid: List[Dict[str, Any]] = []
    for i, c in enumerate(candidates):
        src = (c.get("src") or "").strip()
        if not src or src == ref_norm or src in seen_src:
            continue  # empty, no-op, or duplicate
        if not compiles(src, function_name):
            print(f"[acquire] dropping mutant {c.get('id', i)} (does not compile)")
            continue
        seen_src.add(src)
        valid.append(
            {
                "id": c.get("id") or f"mut_{i}",
                "description": c.get("description", ""),
                "src": src,
            }
        )
    return valid


def acquire_target(repo_url: str, path: str, function_name: str, n_mutants: int = 5) -> Target:
    language = _language_for(path)
    reference_src = fetch_file(repo_url, path)
    print(f"[acquire] {repo_url} :: {path} ({language}), target `{function_name}`")

    # The reference itself must compile/export the target, else nothing downstream works.
    compiles = _compiles_fn(language)
    if not compiles(reference_src, function_name):
        raise RuntimeError(
            f"reference does not compile or export `{function_name}` in a standalone harness "
            f"(file may rely on imports). Pick a self-contained function for now."
        )

    mutants = generate_mutants(reference_src, function_name, language, n_mutants)
    if not mutants:
        raise RuntimeError("no valid mutants were generated; try a larger n or another function")
    print(f"[acquire] {len(mutants)} valid mutants: {[m['id'] for m in mutants]}")
    return Target(reference_src, mutants, language, function_name)
