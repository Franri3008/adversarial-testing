from typing import Any, Dict

STRATEGY_MODEL = "claude-opus-4-8"
BULK_MODEL = "nebius/open-model-placeholder"

ROUTES = {
    "strategy": STRATEGY_MODEL,
    "bulk": BULK_MODEL,
}


def resolve_model(role: str) -> str:
    return ROUTES.get(role, STRATEGY_MODEL)


def complete(prompt: str, role: str = "strategy", **kwargs: Any) -> Dict[str, Any]:
    model = resolve_model(role);
    fake_text = "STUB_COMPLETION";
    tokens = {"in": max(1, len(prompt) // 4), "out": 64};
    return {"text": fake_text, "model": model, "tokens": tokens}
