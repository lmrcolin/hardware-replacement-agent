"""ClaudeClient (chat option "Claude (API key)") with a fake SDK client: no API calls."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from advisor.config import Settings
from advisor.llm.base import LLMUnavailableError, TemplateClient
from advisor.llm.chain import build_llm_chain
from advisor.models import ParsedQuery

anthropic = pytest.importorskip("anthropic")
from advisor.llm.claude import ClaudeClient  # noqa: E402


class FakeMessages:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response, self.error, self.calls = response, error, []

    def _answer(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response

    parse = create = _answer


def client_with(messages: FakeMessages) -> ClaudeClient:
    client = ClaudeClient("claude-haiku-5-5")
    client._client = SimpleNamespace(messages=messages)
    return client


PARSED = ParsedQuery(original_text="Necesito reemplazar la USB-2627", part_numbers=["USB-2627"])


def test_nlu_returns_the_validated_schema_and_sends_no_sampling_params() -> None:
    usage = SimpleNamespace(input_tokens=1800, output_tokens=120)
    messages = FakeMessages(
        SimpleNamespace(stop_reason="end_turn", parsed_output=PARSED, usage=usage)
    )
    client = client_with(messages)
    result = client.complete_json("prompt", ParsedQuery)
    assert result == PARSED
    call = messages.calls[0]
    assert call["model"] == "claude-haiku-5-5" and call["output_format"] is ParsedQuery
    assert "system" not in call  # the NLU instruction lives in the prompt
    recorded = client.calls[0]
    assert (recorded.kind, recorded.input_tokens, recorded.output_tokens, recorded.ok) == (
        "json",
        1800,
        120,
        True,
    )
    assert call["output_config"] == {"effort": "low"}
    assert not {"temperature", "top_p", "top_k"} & call.keys()  # rejected by API 2026-10-21


def test_nlg_joins_text_blocks_only() -> None:
    content = [
        SimpleNamespace(type="thinking", thinking=""),
        SimpleNamespace(type="text", text="USB-2633 es compatible. "),
    ]
    messages = FakeMessages(SimpleNamespace(stop_reason="end_turn", content=content))
    assert client_with(messages).generate("draft") == "USB-2633 es compatible."
    system = messages.calls[0]["system"]  # brevity rules for the customer-facing text
    assert "sin saludos" in system and "no agregues datos" in system


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_refusal_or_truncation_moves_to_the_next_provider(stop_reason: str) -> None:
    messages = FakeMessages(SimpleNamespace(stop_reason=stop_reason, parsed_output=PARSED))
    client = client_with(messages)
    with pytest.raises(LLMUnavailableError, match=stop_reason):
        client.complete_json("prompt", ParsedQuery)
    assert client.calls[-1].ok is False


def test_api_errors_move_to_the_next_provider() -> None:
    error = anthropic.APIConnectionError(request=SimpleNamespace(method="POST", url="x"))
    with pytest.raises(LLMUnavailableError, match="claude"):
        client_with(FakeMessages(error=error)).generate("draft")


def test_missing_structured_output_is_unavailable() -> None:
    messages = FakeMessages(SimpleNamespace(stop_reason="end_turn", parsed_output=None))
    with pytest.raises(LLMUnavailableError, match="structured"):
        client_with(messages).complete_json("prompt", ParsedQuery)


def test_chat_option_builds_the_real_client_with_haiku(monkeypatch: pytest.MonkeyPatch) -> None:
    from advisor.llm import claude_status

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-a-real-key")
    assert claude_status() == "ready"
    chain = build_llm_chain(Settings(), "claude")
    assert [c.name for c in chain] == ["claude", "template"]
    assert isinstance(chain[0], ClaudeClient) and chain[0].model == "claude-haiku-5-5"
    assert chain[0].effort == "low" and isinstance(chain[-1], TemplateClient)
