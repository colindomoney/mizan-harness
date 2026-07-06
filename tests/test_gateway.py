from types import SimpleNamespace

import openai
import pytest

from mizan import gateway
from mizan.gateway import GatewayError, Response, RunParams, run


class FakeCompletions:
    """Stands in for client.chat.completions; records the request it saw."""

    def __init__(self, *, reply: str = "hello", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))],
            model=kwargs["model"],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=34),
            model_dump=lambda: {"id": "cmpl-fake", "model": kwargs["model"]},
        )


def fake_client(completions: FakeCompletions):
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def test_run_returns_structured_response() -> None:
    completions = FakeCompletions(reply="42")
    resp = run("meaning of life?", "anthropic/claude-sonnet-5", client=fake_client(completions))

    assert isinstance(resp, Response)
    assert resp.text == "42"
    assert resp.model == "anthropic/claude-sonnet-5"
    assert (resp.tokens_in, resp.tokens_out) == (12, 34)
    assert resp.latency_ms >= 0
    assert resp.raw["id"] == "cmpl-fake"


def test_run_passes_params_through() -> None:
    completions = FakeCompletions()
    params = RunParams(temperature=0.7, system_prompt="be brief", max_output_tokens=99)
    run("q", "openai/gpt-5.1", params, client=fake_client(completions))

    assert completions.last_kwargs is not None
    assert completions.last_kwargs["temperature"] == 0.7
    assert completions.last_kwargs["max_tokens"] == 99
    assert completions.last_kwargs["messages"][0] == {"role": "system", "content": "be brief"}
    assert completions.last_kwargs["messages"][1] == {"role": "user", "content": "q"}


def test_web_search_defaults_off() -> None:
    assert RunParams().web_search is False


def test_api_error_becomes_gateway_error() -> None:
    completions = FakeCompletions(error=openai.OpenAIError("no such model"))
    with pytest.raises(GatewayError, match="no such model"):
        run("q", "bad/model-id", client=fake_client(completions))


def test_missing_key_raises_clean_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(gateway.API_KEY_ENV, raising=False)
    monkeypatch.setattr(gateway, "load_dotenv", lambda: None)
    with pytest.raises(GatewayError, match=gateway.API_KEY_ENV):
        gateway.make_client()
