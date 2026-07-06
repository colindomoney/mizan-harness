"""Vercel AI Gateway adapter.

The single provider abstraction: everything in the harness calls ``run()``;
nothing else talks to a vendor SDK. The gateway exposes an OpenAI-compatible
endpoint, so one ``openai`` client with a swapped ``base_url`` reaches every
registered model.
"""

import os
import time

import openai
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"
API_KEY_ENV = "AI_GATEWAY_API_KEY"


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
    """A gateway call failed in a known way (bad model id, auth, API error)."""

    def __init__(self, message: str, *, model: str | None = None) -> None:
        super().__init__(message)
        self.model = model


def make_client() -> openai.OpenAI:
    """Build a gateway client from the environment (reads .env if present)."""
    load_dotenv()
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        raise GatewayError(
            f"{API_KEY_ENV} is not set — copy .env.example to .env and add your gateway key"
        )
    return openai.OpenAI(api_key=api_key, base_url=GATEWAY_BASE_URL)


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
