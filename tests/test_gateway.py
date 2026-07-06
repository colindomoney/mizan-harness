import httpx
import openai
import pytest

from conftest import FakeCompletions, fake_client
from mizan import gateway
from mizan.gateway import GatewayError, Response, RunParams, run


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


def make_status_error(status: int, headers: dict | None = None) -> openai.APIStatusError:
    response = httpx.Response(
        status, headers=headers, request=httpx.Request("POST", "https://gw/v1")
    )
    return openai.APIStatusError(f"http {status}", response=response, body=None)


def test_status_error_carries_status_and_retry_after() -> None:
    completions = FakeCompletions(error=make_status_error(429, {"retry-after": "7"}))
    with pytest.raises(GatewayError) as excinfo:
        run("q", "openai/gpt-5.1", client=fake_client(completions))
    assert excinfo.value.status_code == 429
    assert excinfo.value.retry_after == 7.0


def test_missing_key_raises_clean_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(gateway.API_KEY_ENV, raising=False)
    monkeypatch.setattr(gateway, "load_dotenv", lambda: None)
    with pytest.raises(GatewayError, match=gateway.API_KEY_ENV):
        gateway.make_client()
