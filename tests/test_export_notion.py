import json

import httpx
import pytest

from conftest import make_prompt, make_record, make_run_dir
from mizan.bank import Domain
from mizan.export.notion import (
    NOTION_API,
    NotionExportError,
    cell_properties,
    chunk_blocks,
    chunk_text,
    create_runs_database,
    push_run,
)
from mizan.rundata import load_run


class FakeNotion:
    """MockTransport handler recording requests; configurable existing pages / errors."""

    def __init__(self, *, existing_pages: list[str] | None = None, fail_first: int = 0):
        self.existing_pages = existing_pages or []
        self.fail_first = fail_first  # first N requests return 429
        self.requests: list[tuple[str, str, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        self.requests.append((request.method, request.url.path, body))
        if self.fail_first > 0:
            self.fail_first -= 1
            return httpx.Response(429, headers={"Retry-After": "7"}, json={})
        if request.url.path.endswith("/query"):
            return httpx.Response(
                200,
                json={"results": [{"id": pid} for pid in self.existing_pages], "has_more": False},
            )
        if request.url.path == "/v1/databases":
            return httpx.Response(200, json={"data_sources": [{"id": "ds-123"}]})
        return httpx.Response(200, json={"id": "page-new"})


def _client(handler: FakeNotion) -> httpx.Client:
    return httpx.Client(base_url=NOTION_API, transport=httpx.MockTransport(handler))


def _data(tmp_path, records=None, prompts=None):
    prompts = prompts or [make_prompt("a1", Domain.HISTORY)]
    records = records if records is not None else [make_record("a1", "openai/gpt-x")]
    return load_run(make_run_dir(tmp_path, prompts, records))


def test_chunk_text_prefers_newlines_and_respects_limit():
    text = ("line one\n" * 300).strip()  # ~2700 chars
    chunks = chunk_text(text)
    assert all(len(c) <= 2000 for c in chunks)
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")
    assert chunks[0].endswith("line one")  # split at a newline, not mid-line


def test_chunk_text_hard_splits_without_newlines():
    chunks = chunk_text("x" * 4500)
    assert [len(c) for c in chunks] == [2000, 2000, 500]


def test_chunk_blocks_caps_block_count():
    blocks = chunk_blocks("x" * 2000 * 150)  # 150 chunks > 100 cap
    assert len(blocks) == 100
    assert blocks[-1]["paragraph"]["rich_text"][0]["text"]["content"] == "… [truncated]"


def test_cell_properties_missing_and_full():
    prompt = make_prompt("a1", Domain.HISTORY, pair_id="p1")
    model = {"id": "openai/gpt-x", "provider": "openai", "display_name": "GPT-X"}

    props = cell_properties(prompt, model, None, "run-1")
    assert props["Refusal flag"] == {"select": {"name": "missing"}}
    assert props["Run"] == {"select": {"name": "run-1"}}
    assert "Tokens out" not in props

    record = make_record("a1", "openai/gpt-x", text="y" * 3000)
    props = cell_properties(prompt, model, record, "run-1")
    assert props["Tokens out"] == {"number": 5}
    assert props["Response chars"] == {"number": 3000}
    preview = props["Response preview"]["rich_text"][0]["text"]["content"]
    assert len(preview) <= 2000 and preview.endswith("…")
    assert props["Pair ID"]["rich_text"][0]["text"]["content"] == "p1"


def test_push_run_creates_pages_and_throttles(tmp_path):
    handler = FakeNotion()
    sleeps: list[float] = []
    pushed = push_run(
        _data(tmp_path),
        client=_client(handler),
        data_source_id="ds-123",
        sleep=sleeps.append,
    )

    assert pushed == 2  # 1 prompt × 2 models (missing cell pushed too)
    creates = [r for r in handler.requests if r[1] == "/v1/pages"]
    assert len(creates) == 2
    body = creates[0][2]
    assert body["parent"] == {"type": "data_source_id", "data_source_id": "ds-123"}
    assert body["children"][0]["paragraph"]["rich_text"][0]["text"]["content"] == "hello"
    assert "children" not in creates[1][2]  # missing cell has no response body
    assert len(sleeps) == 2  # one throttle sleep per page


def test_push_run_aborts_on_existing_without_force(tmp_path):
    handler = FakeNotion(existing_pages=["old-1"])
    with pytest.raises(NotionExportError, match="--force"):
        push_run(
            _data(tmp_path), client=_client(handler), data_source_id="ds-123", sleep=lambda s: None
        )
    assert all(m != "POST" or p.endswith("/query") for m, p, _ in handler.requests)


def test_push_run_force_archives_then_pushes(tmp_path):
    handler = FakeNotion(existing_pages=["old-1", "old-2"])
    push_run(
        _data(tmp_path),
        client=_client(handler),
        data_source_id="ds-123",
        force=True,
        sleep=lambda s: None,
    )
    archives = [(m, p, b) for m, p, b in handler.requests if m == "PATCH"]
    assert [p for _, p, _ in archives] == ["/v1/pages/old-1", "/v1/pages/old-2"]
    assert all(b == {"archived": True} for _, _, b in archives)


def test_request_retries_429_with_retry_after(tmp_path):
    handler = FakeNotion(fail_first=1)
    sleeps: list[float] = []
    push_run(_data(tmp_path), client=_client(handler), data_source_id="ds-123", sleep=sleeps.append)
    assert 7.0 in sleeps  # honoured Retry-After header


def test_create_runs_database(tmp_path):
    handler = FakeNotion()
    ds_id = create_runs_database(
        client=_client(handler), parent_page_id="parent-1", sleep=lambda s: None
    )
    assert ds_id == "ds-123"
    method, path, body = handler.requests[0]
    assert (method, path) == ("POST", "/v1/databases")
    assert body["parent"] == {"type": "page_id", "page_id": "parent-1"}
    props = body["initial_data_source"]["properties"]
    assert props["Query"] == {"title": {}}
    assert {o["name"] for o in props["Refusal flag"]["select"]["options"]} >= {
        "answered",
        "refused",
        "missing",
    }
