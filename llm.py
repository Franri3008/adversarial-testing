import os
import sys
from typing import Any, Dict

try:
    from dotenv import load_dotenv
    load_dotenv();
except Exception as _dotenv_exc:
    print("[llm] python-dotenv unavailable, relying on process environment: {}".format(_dotenv_exc), file=sys.stderr);

STRATEGY_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8");
BULK_MODEL = os.environ.get("NEBIUS_MODEL", "Qwen/Qwen3-30B-A3B-Instruct-2507");
DEFAULT_NEBIUS_BASE_URL = "https://api.studio.nebius.com/v1";
DEFAULT_MAX_TOKENS = 4096;

ROUTES = {
    "strategy": STRATEGY_MODEL,
    "bulk": BULK_MODEL,
};

CLAUDE_UNSUPPORTED_KWARGS = ("temperature", "top_p", "top_k");


def resolve_model(role: str) -> str:
    return ROUTES.get(role, STRATEGY_MODEL)


def _warn(message: str) -> None:
    print("[llm] " + message, file=sys.stderr);


def _stub(prompt: str, model: str) -> Dict[str, Any]:
    tokens = {"in": max(1, len(prompt) // 4), "out": 64};
    return {"text": "STUB_COMPLETION", "model": model, "tokens": tokens}


def _complete_strategy(prompt: str, model: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.environ.get("ANTHROPIC_APIKEY") or os.environ.get("ANTHROPIC_API_KEY");
    if not api_key:
        raise RuntimeError("ANTHROPIC_APIKEY not set");
    import anthropic
    client = anthropic.Anthropic(api_key=api_key);
    params = {k: v for k, v in kwargs.items() if k not in CLAUDE_UNSUPPORTED_KWARGS};
    max_tokens = params.pop("max_tokens", DEFAULT_MAX_TOKENS);
    response = client.messages.create(model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}], **params);
    text = "".join(getattr(block, "text", "") for block in response.content if getattr(block, "type", "") == "text");
    tokens = {"in": int(response.usage.input_tokens), "out": int(response.usage.output_tokens)};
    return {"text": text, "model": model, "tokens": tokens}


def _complete_bulk(prompt: str, model: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.environ.get("NEBIUS_APIKEY") or os.environ.get("NEBIUS_API_KEY");
    if not api_key:
        raise RuntimeError("NEBIUS_APIKEY not set");
    base_url = os.environ.get("NEBIUS_BASE_URL", DEFAULT_NEBIUS_BASE_URL);
    import openai
    client = openai.OpenAI(api_key=api_key, base_url=base_url);
    params = dict(kwargs);
    max_tokens = params.pop("max_tokens", DEFAULT_MAX_TOKENS);
    response = client.chat.completions.create(model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}], **params);
    text = response.choices[0].message.content or "";
    usage = response.usage;
    tokens = {"in": int(usage.prompt_tokens), "out": int(usage.completion_tokens)};
    return {"text": text, "model": model, "tokens": tokens}


def complete(prompt: str, role: str = "strategy", **kwargs: Any) -> Dict[str, Any]:
    model = resolve_model(role);
    try:
        if role == "bulk":
            return _complete_bulk(prompt, model, kwargs)
        return _complete_strategy(prompt, model, kwargs)
    except Exception as exc:
        _warn("{} call failed ({}: {}); using stub fallback".format(role, type(exc).__name__, exc));
        return _stub(prompt, model)
