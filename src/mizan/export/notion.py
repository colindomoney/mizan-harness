"""Push a run into the master "Mizan runs" Notion database — one page per cell.

A single data source holds every run, distinguished by a ``Run`` select
property, so Notion views can filter and group across runs. Structured fields
land as page properties; the full response text goes into the page body as
paragraph blocks chunked under Notion's 2000-char rich-text limit.

The one-time database bootstrap (``create_runs_database``) prints a
data_source_id the caller stores as ``NOTION_RUNS_DATA_SOURCE_ID`` in ``.env``.
API conventions (httpx client shape, version, data-source endpoints) follow
``scripts/export_bank.py``.
"""

import time
from collections.abc import Callable

import httpx

from mizan.bank import Domain, PromptRecord
from mizan.records import RunRecord
from mizan.rundata import RunData, effective_flag

from .summary import FLAG_NAMES

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2025-09-03"  # first version with data-source endpoints
REQUEST_INTERVAL_S = 0.35  # ~3 requests/second, Notion's documented ceiling
MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 2.0

_RICH_TEXT_LIMIT = 2000
_PREVIEW_CHARS = 1900
_TITLE_CHARS = 200
_MAX_BODY_BLOCKS = 100  # Notion's cap on children in a page-create call


class NotionExportError(Exception):
    """The push could not proceed (existing pages without --force, API failure)."""


def make_client(api_key: str) -> httpx.Client:
    return httpx.Client(
        base_url=NOTION_API,
        headers={"Authorization": f"Bearer {api_key}", "Notion-Version": NOTION_VERSION},
        timeout=30,
    )


def _request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    json_body: dict | None = None,
    sleep=time.sleep,
) -> httpx.Response:
    """One API call with retry on 429/5xx, honouring Retry-After."""
    resp: httpx.Response | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        resp = client.request(method, url, json=json_body)
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == MAX_ATTEMPTS:
                break
            retry_after = resp.headers.get("Retry-After")
            sleep(float(retry_after) if retry_after else BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))
            continue
        resp.raise_for_status()
        return resp
    raise NotionExportError(
        f"{method} {url} failed after {MAX_ATTEMPTS} attempts: {resp.status_code} {resp.text[:200]}"
    )


def chunk_text(text: str, limit: int = _RICH_TEXT_LIMIT) -> list[str]:
    """Split text into ≤limit-char chunks, preferring newline boundaries."""
    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        cut = rest.rfind("\n", limit // 2, limit)
        if cut == -1:
            cut = limit
        chunks.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    return chunks


def _paragraph(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def chunk_blocks(text: str) -> list[dict]:
    """Full response text as paragraph blocks, capped at Notion's per-create limit."""
    blocks = [_paragraph(chunk) for chunk in chunk_text(text)]
    if len(blocks) > _MAX_BODY_BLOCKS:
        blocks = blocks[: _MAX_BODY_BLOCKS - 1] + [_paragraph("… [truncated]")]
    return blocks


def _rich_text(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": text[:_RICH_TEXT_LIMIT]}}]


def cell_properties(
    prompt: PromptRecord, model: dict, record: RunRecord | None, run_id: str
) -> dict:
    props: dict = {
        "Query": {"title": [{"type": "text", "text": {"content": prompt.query[:_TITLE_CHARS]}}]},
        "Run": {"select": {"name": run_id}},
        "Prompt ID": {"rich_text": _rich_text(prompt.id)},
        "Domain": {"select": {"name": str(prompt.domain)}},
        "Model": {"select": {"name": model["display_name"]}},
        "Provider": {"select": {"name": model["provider"]}},
        "Refusal flag": {"select": {"name": effective_flag(record)}},
    }
    if prompt.pair_id:
        props["Pair ID"] = {"rich_text": _rich_text(prompt.pair_id)}
    if record is None:
        return props

    props["Gateway"] = {"select": {"name": record.gateway}}
    props["Timestamp"] = {"date": {"start": record.timestamp.isoformat()}}
    for name, value in (
        ("Tokens in", record.tokens_in),
        ("Tokens out", record.tokens_out),
        ("Latency ms", record.latency_ms),
    ):
        if value is not None:
            props[name] = {"number": value}
    if record.error is not None:
        props["Error"] = {"rich_text": _rich_text(record.error)}
    if record.response_text:
        text = record.response_text
        props["Response chars"] = {"number": len(text)}
        preview = text[:_PREVIEW_CHARS] + ("…" if len(text) > _PREVIEW_CHARS else "")
        props["Response preview"] = {"rich_text": _rich_text(preview)}
    return props


_DB_PROPERTIES: dict = {
    "Query": {"title": {}},
    "Run": {"select": {}},
    "Prompt ID": {"rich_text": {}},
    "Domain": {"select": {"options": [{"name": str(d)} for d in Domain]}},
    "Pair ID": {"rich_text": {}},
    "Model": {"select": {}},
    "Provider": {"select": {}},
    "Gateway": {"select": {}},
    "Refusal flag": {"select": {"options": [{"name": f} for f in FLAG_NAMES]}},
    "Tokens in": {"number": {}},
    "Tokens out": {"number": {}},
    "Latency ms": {"number": {}},
    "Response chars": {"number": {}},
    "Error": {"rich_text": {}},
    "Response preview": {"rich_text": {}},
    "Timestamp": {"date": {}},
}


def create_runs_database(*, client: httpx.Client, parent_page_id: str, sleep=time.sleep) -> str:
    """One-time bootstrap: create the master runs database, return its data_source_id."""
    resp = _request(
        client,
        "POST",
        "/databases",
        json_body={
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": "Mizan runs"}}],
            "initial_data_source": {"properties": _DB_PROPERTIES},
        },
        sleep=sleep,
    )
    return resp.json()["data_sources"][0]["id"]


def existing_run_pages(
    *, client: httpx.Client, data_source_id: str, run_id: str, sleep=time.sleep
) -> list[str]:
    """Page ids already pushed for this run (idempotency check)."""
    page_ids: list[str] = []
    cursor: str | None = None
    while True:
        body: dict = {
            "filter": {"property": "Run", "select": {"equals": run_id}},
            "page_size": 100,
        }
        if cursor:
            body["start_cursor"] = cursor
        data = _request(
            client, "POST", f"/data_sources/{data_source_id}/query", json_body=body, sleep=sleep
        ).json()
        page_ids.extend(page["id"] for page in data["results"])
        if not data.get("has_more"):
            return page_ids
        cursor = data["next_cursor"]


def push_run(
    data: RunData,
    *,
    client: httpx.Client,
    data_source_id: str,
    sleep=time.sleep,
    force: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
) -> int:
    """Push every cell of a run as a Notion page; returns the page count.

    Aborts if the run was already pushed, unless ``force`` — which archives the
    prior pages first so a re-push (e.g. after resuming a run) replaces cleanly.
    """
    existing = existing_run_pages(
        client=client, data_source_id=data_source_id, run_id=data.run_id, sleep=sleep
    )
    if existing and not force:
        raise NotionExportError(
            f"run {data.run_id} already has {len(existing)} pages in Notion; "
            "re-run with --force to archive and replace them"
        )
    for page_id in existing:
        _request(client, "PATCH", f"/pages/{page_id}", json_body={"archived": True}, sleep=sleep)
        sleep(REQUEST_INTERVAL_S)

    total = len(data.prompts) * len(data.models)
    pushed = 0
    for prompt in data.prompts:
        for model in data.models:
            record = data.cells.get((prompt.id, model["id"]))
            body: dict = {
                "parent": {"type": "data_source_id", "data_source_id": data_source_id},
                "properties": cell_properties(prompt, model, record, data.run_id),
            }
            if record is not None and record.response_text:
                body["children"] = chunk_blocks(record.response_text)
            _request(client, "POST", "/pages", json_body=body, sleep=sleep)
            pushed += 1
            if on_progress:
                on_progress(pushed, total)
            sleep(REQUEST_INTERVAL_S)
    return pushed
