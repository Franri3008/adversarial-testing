"""Backend contract: stub is explicit & deterministic; real backends fail loud."""
import pytest

import llm


def test_stub_backend_is_deterministic(monkeypatch):
    monkeypatch.setattr(llm, "BACKEND", "stub")
    out = llm.complete("anything", role="strategy")
    assert out["text"] == "STUB_COMPLETION"
    assert out["cost"] == 0.0
    assert out["tokens"]["out"] == 64


def test_sdk_strategy_without_key_raises(monkeypatch):
    monkeypatch.setattr(llm, "BACKEND", "sdk")
    monkeypatch.delenv("ANTHROPIC_APIKEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="strategy call failed under BACKEND=sdk"):
        llm.complete("x", role="strategy")


def test_sdk_bulk_without_key_raises(monkeypatch):
    monkeypatch.setattr(llm, "BACKEND", "sdk")
    monkeypatch.delenv("NEBIUS_APIKEY", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="bulk call failed under BACKEND=sdk"):
        llm.complete("x", role="bulk")
