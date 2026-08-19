"""Tests for src/agent/deepteam_groq_model.py's GroqDeepEvalModel wrapper.

Covers only the deterministic parts (request/response shape, retry-on-429
behaviour) with a mocked chat model -- no live Groq calls, same pattern as
tests/test_ml_guardrail.py's fake classifier. deepteam's own red-teaming
logic is a third-party library and is not covered here; see
experiments/deepteam_redteam_eval.py for the manually-run, live-call script.
"""

import asyncio

import pytest

import src.agent.deepteam_groq_model as deepteam_groq_model
from src.agent.deepteam_groq_model import GroqDeepEvalModel


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _FakeChatModel:
    """invoke() returns a canned response, or raises canned exceptions in
    sequence (to simulate a 429 followed by a success)."""

    def __init__(self, responses=None, exceptions=None):
        self.responses = list(responses or [])
        self.exceptions = list(exceptions or [])
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        if self.exceptions:
            raise self.exceptions.pop(0)
        return _FakeResponse(self.responses.pop(0))


def _make_model(monkeypatch, fake_chat_model):
    monkeypatch.setattr(
        deepteam_groq_model,
        "ChatGroq",
        lambda model, temperature, max_tokens: fake_chat_model,
    )
    return GroqDeepEvalModel(model_name="llama-3.1-8b-instant")


def test_get_model_name_is_prefixed_with_groq(monkeypatch):
    model = _make_model(monkeypatch, _FakeChatModel(responses=["ok"]))
    assert model.get_model_name() == "Groq/llama-3.1-8b-instant"


def test_generate_returns_the_chat_model_response_content(monkeypatch):
    fake = _FakeChatModel(responses=["the verdict is TruePositive"])
    model = _make_model(monkeypatch, fake)

    result = model.generate("triage this alert")

    assert result == "the verdict is TruePositive"
    assert fake.calls == 1


def test_a_generate_wraps_the_sync_call(monkeypatch):
    fake = _FakeChatModel(responses=["async verdict"])
    model = _make_model(monkeypatch, fake)

    result = asyncio.run(model.a_generate("triage this alert"))

    assert result == "async verdict"


def test_retries_once_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(deepteam_groq_model.time, "sleep", lambda seconds: None)
    fake = _FakeChatModel(
        responses=["recovered"],
        exceptions=[RuntimeError("rate_limit_exceeded: please try again in 1.2s")],
    )
    model = _make_model(monkeypatch, fake)

    result = model.generate("triage this alert")

    assert result == "recovered"
    assert fake.calls == 2


def test_non_rate_limit_error_is_not_retried(monkeypatch):
    fake = _FakeChatModel(exceptions=[ValueError("some other failure")])
    model = _make_model(monkeypatch, fake)

    with pytest.raises(ValueError):
        model.generate("triage this alert")

    assert fake.calls == 1


def test_exhausting_retries_raises_runtime_error(monkeypatch):
    monkeypatch.setattr(deepteam_groq_model.time, "sleep", lambda seconds: None)
    fake = _FakeChatModel(
        exceptions=[RuntimeError("429 please try again in 0.1s")] * deepteam_groq_model.MAX_RETRIES
    )
    model = _make_model(monkeypatch, fake)

    with pytest.raises(RuntimeError, match="Groq call failed after"):
        model.generate("triage this alert")

    assert fake.calls == deepteam_groq_model.MAX_RETRIES


def test_valid_json_passes_through_with_no_repair_call(monkeypatch):
    fake = _FakeChatModel(responses=['{"verdict": "TruePositive"}'])
    model = _make_model(monkeypatch, fake)

    result = model.generate("respond with json")

    assert result == '{"verdict": "TruePositive"}'
    assert fake.calls == 1


def test_markdown_fenced_json_is_stripped_with_no_repair_call(monkeypatch):
    fake = _FakeChatModel(responses=['```json\n{"verdict": "TruePositive"}\n```'])
    model = _make_model(monkeypatch, fake)

    result = model.generate("respond with json")

    assert result == '{"verdict": "TruePositive"}'
    assert fake.calls == 1


def test_plain_text_response_is_left_untouched_with_no_repair_call(monkeypatch):
    fake = _FakeChatModel(responses=["I'm sorry, but I can't help with that."])
    model = _make_model(monkeypatch, fake)

    result = model.generate("respond with json")

    assert result == "I'm sorry, but I can't help with that."
    assert fake.calls == 1


def test_malformed_json_triggers_one_repair_call_that_succeeds(monkeypatch):
    fake = _FakeChatModel(
        responses=[
            '{"verdict": TruePositive}',  # malformed: unquoted value, not just a trailing comma
            '{"verdict": "TruePositive", "note": "fixed"}',  # repair call's response
        ]
    )
    model = _make_model(monkeypatch, fake)

    result = model.generate("respond with json")

    assert result == '{"verdict": "TruePositive", "note": "fixed"}'
    assert fake.calls == 2


def test_malformed_json_falls_back_to_original_if_repair_also_fails(monkeypatch):
    fake = _FakeChatModel(
        responses=[
            "{not json at all",
            "{still not json",
        ]
    )
    model = _make_model(monkeypatch, fake)

    result = model.generate("respond with json")

    assert result == "{not json at all"
    assert fake.calls == 2
