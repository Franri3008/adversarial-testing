import json
import os
import subprocess
import sys
from typing import Any, Dict


def _load_dotenv(path: str = ".env") -> None:
    """Load a local .env into the environment.

    Prefer python-dotenv when installed; otherwise parse .env ourselves so a local
    .env works with zero extra dependencies (avoids PEP 668 install friction).
    Existing process env vars win — .env only fills what is not already set.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv();
        return
    except Exception:
        pass
    try:
        with open(path) as handle:
            for raw in handle:
                line = raw.strip();
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[len("export "):];
                key, _, value = line.partition("=");
                key = key.strip();
                value = value.strip().strip('"').strip("'");
                if key:
                    os.environ.setdefault(key, value);
    except FileNotFoundError:
        pass


_load_dotenv();


STRATEGY_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8");
BULK_MODEL = os.environ.get("NEBIUS_MODEL", "Qwen/Qwen3-30B-A3B-Instruct-2507");
DEFAULT_NEBIUS_BASE_URL = "https://api.studio.nebius.com/v1";
DEFAULT_MAX_TOKENS = 4096;

# Strategy transport. Default routes the strategist to Anthropic (opus). Set
# STRATEGY_PROVIDER=nebius to run the strategist on a strong open model instead
# (e.g. when Anthropic credits are unavailable) — same OpenAI-compatible path as bulk.
STRATEGY_PROVIDER = os.environ.get("STRATEGY_PROVIDER", "anthropic");
STRATEGY_NEBIUS_MODEL = os.environ.get("STRATEGY_NEBIUS_MODEL", "Qwen/Qwen3-235B-A22B-Instruct-2507");

STRATEGY_RATE_PER_MTOK = (
    float(os.environ.get("STRATEGY_IN_RATE", "5.0")),
    float(os.environ.get("STRATEGY_OUT_RATE", "25.0")),
);
BULK_RATE_PER_MTOK = (
    float(os.environ.get("BULK_IN_RATE", "0.1")),
    float(os.environ.get("BULK_OUT_RATE", "0.3")),
);

ROUTES = {
    "strategy": STRATEGY_MODEL,
    "bulk": BULK_MODEL,
};

CLAUDE_UNSUPPORTED_KWARGS = ("temperature", "top_p", "top_k");

# Backend transport. "cli" runs the local `claude -p` (uses the machine's Claude Code
# auth/gateway — no SDK install, no API key needed), which is what makes this loop
# runnable on a laptop out of the box. "sdk" uses the original anthropic/openai paths.
# "stub" is the explicit offline backend: it returns a deterministic STUB_COMPLETION for
# every call (no network). The repair helpers branch on that sentinel to fall back to
# their seed bugs / oracle fixes, so `BACKEND=stub` drives the reproducible offline demo.
BACKEND = os.environ.get("BACKEND", "cli");
CLI_MODELS = {
    "strategy": os.environ.get("STRATEGY_MODEL", "opus"),
    "bulk": os.environ.get("BULK_MODEL", "haiku"),
};
CLI_TIMEOUT = int(os.environ.get("CLI_TIMEOUT", "180"));


def resolve_model(role: str) -> str:
    return ROUTES.get(role, STRATEGY_MODEL)


def _warn(message: str) -> None:
    print("[llm] " + message, file=sys.stderr);


def _stub(prompt: str, model: str) -> Dict[str, Any]:
    tokens = {"in": max(1, len(prompt) // 4), "out": 64};
    return {"text": "STUB_COMPLETION", "model": model, "tokens": tokens, "cost": 0.0}


def _cost(tokens: Dict[str, int], rate_per_mtok: Any) -> float:
    in_rate, out_rate = rate_per_mtok;
    return tokens["in"] / 1e6 * in_rate + tokens["out"] / 1e6 * out_rate


def _complete_cli(prompt: str, role: str) -> Dict[str, Any]:
    """Transport via the local `claude -p`. Two-tier: strategy->opus, bulk->haiku."""
    model = CLI_MODELS.get(role, "sonnet");
    proc = subprocess.run(
        ["claude", "-p", prompt, "--model", model, "--output-format", "json"],
        capture_output=True,
        text=True,
        timeout=CLI_TIMEOUT,
    );
    if proc.returncode != 0:
        detail = proc.stderr.strip();
        try:
            detail = json.loads(proc.stdout).get("result") or detail;
        except Exception:
            pass
        raise RuntimeError("claude cli exit {}: {}".format(proc.returncode, (detail or "<no output>")[:200]));
    data = json.loads(proc.stdout);
    if data.get("is_error"):
        raise RuntimeError("claude cli reported error: {}".format(data.get("result"))[:200]);
    usage = data.get("usage", {}) or {};
    tokens = {
        "in": int(usage.get("input_tokens", 0)),
        "out": int(usage.get("output_tokens", 0)),
    };
    return {
        "text": data.get("result", ""),
        "model": model,
        "tokens": tokens,
        "cost": float(data.get("total_cost_usd", 0.0)),
    }



def _complete_strategy(prompt: str, model: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.environ.get("ANTHROPIC_APIKEY") or os.environ.get("ANTHROPIC_API_KEY");
    if not api_key:
        raise RuntimeError("ANTHROPIC_APIKEY not set");
    import anthropic
    client = anthropic.Anthropic(api_key=api_key);
    # temperature/top_p/top_k are intentionally stripped (CLAUDE_UNSUPPORTED_KWARGS) — some
    # Claude models reject a non-default temperature, so we leave decoding to the API default.
    params = {k: v for k, v in kwargs.items() if k not in CLAUDE_UNSUPPORTED_KWARGS};
    max_tokens = params.pop("max_tokens", DEFAULT_MAX_TOKENS);
    # Prompt caching: callers can pass a `cache_prefix` (stable text — system
    # instructions, reference src, etc) that we send as its own content block with
    # cache_control. Subsequent calls within ~5min that share the same prefix get
    # a cache hit, slashing input cost (~10%) and latency. The variable `prompt`
    # follows in a normal block.
    cache_prefix = params.pop("cache_prefix", None);
    if cache_prefix:
        content = [
            {"type": "text", "text": cache_prefix, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": prompt},
        ];
    else:
        content = prompt;
    # Stream always. Mutant generation asks for n full-file copies, so max_tokens can be
    # tens of thousands; a non-streaming create() then raises "Streaming is required for
    # operations that may take longer than 10 minutes" before it ever calls the API.
    # Streaming sidesteps that hard cap and is the recommended path for long outputs;
    # get_final_message() reassembles the whole response (and its usage) for us.
    with client.messages.stream(model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": content}], **params) as stream:
        response = stream.get_final_message();
    text = "".join(getattr(block, "text", "") for block in response.content if getattr(block, "type", "") == "text");
    usage = response.usage;
    cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0);
    cache_write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0);
    fresh_in = int(usage.input_tokens);
    # Total input for budget accounting includes cached reads/writes (API reports
    # them separately). Cost reflects the actual billed mix: writes ~1.25x, reads ~0.1x.
    tokens = {"in": fresh_in + cache_read + cache_write, "out": int(usage.output_tokens)};
    in_rate, out_rate = STRATEGY_RATE_PER_MTOK;
    cost = (
        fresh_in / 1e6 * in_rate
        + cache_write / 1e6 * in_rate * 1.25
        + cache_read / 1e6 * in_rate * 0.1
        + tokens["out"] / 1e6 * out_rate
    );
    return {"text": text, "model": model, "tokens": tokens, "cost": cost}


def _complete_bulk(prompt: str, model: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.environ.get("NEBIUS_APIKEY") or os.environ.get("NEBIUS_API_KEY");
    if not api_key:
        raise RuntimeError("NEBIUS_APIKEY not set");
    base_url = os.environ.get("NEBIUS_BASE_URL", DEFAULT_NEBIUS_BASE_URL);
    import openai
    client = openai.OpenAI(api_key=api_key, base_url=base_url);
    params = dict(kwargs);
    # Greedy decoding by default for reproducible runs (callers may override).
    params.setdefault("temperature", 0);
    max_tokens = params.pop("max_tokens", DEFAULT_MAX_TOKENS);
    response = client.chat.completions.create(model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}], **params);
    text = response.choices[0].message.content or "";
    usage = response.usage;
    tokens = {"in": int(usage.prompt_tokens), "out": int(usage.completion_tokens)};
    return {"text": text, "model": model, "tokens": tokens, "cost": _cost(tokens, BULK_RATE_PER_MTOK)}


def complete(prompt: str, role: str = "strategy", **kwargs: Any) -> Dict[str, Any]:
    model = resolve_model(role);
    # cache_prefix is only honored by the Anthropic SDK path. For other backends
    # we concatenate it onto the prompt so the model still sees the same text —
    # we just don't get the cache discount.
    cache_prefix = kwargs.get("cache_prefix");
    joined_prompt = (cache_prefix + "\n\n" + prompt) if cache_prefix else prompt;
    # Explicit offline backend: deterministic STUB_COMPLETION, no network. The only path
    # that is allowed to return a stub.
    if BACKEND == "stub":
        return _stub(joined_prompt, model)
    # Real backends fail LOUD: an auth/rate-limit/transport error must surface, not be
    # silently swallowed into a stub that looks like a legitimate (empty) result. Use
    # BACKEND=stub if you want the offline path.
    try:
        if BACKEND == "cli":
            return _complete_cli(joined_prompt, role)
        if role == "bulk":
            return _complete_bulk(joined_prompt, model, {k: v for k, v in kwargs.items() if k != "cache_prefix"})
        if STRATEGY_PROVIDER == "nebius":
            return _complete_bulk(joined_prompt, STRATEGY_NEBIUS_MODEL, {k: v for k, v in kwargs.items() if k != "cache_prefix"})
        return _complete_strategy(prompt, model, kwargs)
    except Exception as exc:
        raise RuntimeError(
            "{} call failed under BACKEND={} ({}: {}). "
            "Fix the backend/credentials, or set BACKEND=stub for the offline path.".format(
                role, BACKEND, type(exc).__name__, exc)
        ) from exc
