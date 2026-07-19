"""OpenAI-compatible gateway adapter (OpenRouter default, Vercel alternative).

The single provider abstraction: everything in the harness calls ``run()``;
nothing else talks to a vendor SDK. Both supported gateways expose an
OpenAI-compatible endpoint, so one ``openai`` client with a swapped
``base_url`` reaches every registered model through either.
"""

import os
import time

import openai
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict


class GatewayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    base_url: str
    api_key_env: str
    key_hint: str  # where to mint a key, for the missing-key error


GATEWAYS: dict[str, GatewayConfig] = {
    "openrouter": GatewayConfig(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        key_hint="create one at https://openrouter.ai/settings/keys",
    ),
    "vercel": GatewayConfig(
        name="vercel",
        base_url="https://ai-gateway.vercel.sh/v1",
        api_key_env="VERCEL_AI_GATEWAY_API_KEY",
        key_hint="create one at https://vercel.com/docs/ai-gateway",
    ),
}
DEFAULT_GATEWAY = "openrouter"


class RunParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float = 0.0
    system_prompt: str | None = None
    # Recorded on every run for reproducibility, but not yet wired to any
    # provider capability — app-level web search is a later axis.
    web_search: bool = False
    max_output_tokens: int = 4096


class Response(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    raw: dict


class GatewayError(Exception):
    """A gateway call failed in a known way (bad model id, auth, API error).

    ``status_code``/``retry_after`` let callers distinguish transient failures
    (429, 5xx) worth retrying from permanent ones (bad model id, auth).
    """

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.model = model
        self.status_code = status_code
        self.retry_after = retry_after


def make_client(gateway_name: str = DEFAULT_GATEWAY) -> openai.OpenAI:
    """Build a client for the named gateway from the environment (reads .env if present)."""
    cfg = GATEWAYS.get(gateway_name)
    if cfg is None:
        raise GatewayError(f"unknown gateway {gateway_name!r}; choose from {sorted(GATEWAYS)}")
    load_dotenv()
    api_key = os.environ.get(cfg.api_key_env)
    if not api_key:
        raise GatewayError(
            f"{cfg.api_key_env} is not set — copy .env.example to .env and add your "
            f"{cfg.name} key ({cfg.key_hint})"
        )
    return openai.OpenAI(api_key=api_key, base_url=cfg.base_url)


def run(
    prompt: str,
    model: str,
    params: RunParams | None = None,
    *,
    client: openai.OpenAI | None = None,
) -> Response:
    """Run one prompt against one model through the gateway.

    ``model`` is a gateway slug from the registry (e.g. ``anthropic/claude-sonnet-5``).
    """
    params = params or RunParams()
    if client is None:
        client = make_client()

    messages: list[dict] = []
    if params.system_prompt:
        messages.append({"role": "system", "content": params.system_prompt})
    messages.append({"role": "user", "content": prompt})

    start = time.perf_counter()
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=params.temperature,
            max_tokens=params.max_output_tokens,
        )
    except openai.APIStatusError as exc:
        header = exc.response.headers.get("retry-after")
        retry_after = float(header) if header and header.replace(".", "", 1).isdigit() else None
        raise GatewayError(
            f"gateway call failed for {model}: {exc}",
            model=model,
            status_code=exc.status_code,
            retry_after=retry_after,
        ) from exc
    except openai.OpenAIError as exc:
        raise GatewayError(f"gateway call failed for {model}: {exc}", model=model) from exc
    latency_ms = int((time.perf_counter() - start) * 1000)

    usage = completion.usage
    return Response(
        text=completion.choices[0].message.content or "",
        model=completion.model or model,
        tokens_in=usage.prompt_tokens if usage else 0,
        tokens_out=usage.completion_tokens if usage else 0,
        latency_ms=latency_ms,
        raw=completion.model_dump(),
    )
