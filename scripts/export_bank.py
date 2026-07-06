"""Export the Notion Prompt Bank to prompts/bank.jsonl.

Notion stays the editing surface; this script produces the frozen, committed
snapshot the harness runs against. Re-export is a deliberate, reviewable step:
output is sorted by record id, so re-runs diff cleanly.

Usage:
    NOTION_API_KEY=secret_... uv run python scripts/export_bank.py
    uv run python scripts/export_bank.py --data-source-id <uuid> --out prompts/bank.jsonl

The integration behind NOTION_API_KEY must be connected to the Prompt Bank
database in Notion (Share → connections).
"""

import argparse
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

from mizan.bank import PromptRecord

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2025-09-03"  # first version with data-source endpoints
DEFAULT_DATA_SOURCE_ID = "e2a212b4-3cec-4fec-9460-2bd352b5936f"


def _plain_text(prop: dict) -> str:
    """Join the plain_text of a title/rich_text property."""
    fragments = prop.get("title") or prop.get("rich_text") or []
    return "".join(f["plain_text"] for f in fragments).strip()


def _to_record(page: dict) -> PromptRecord:
    props = page["properties"]
    pair_id = _plain_text(props["Pair ID"])
    return PromptRecord(
        id=page["id"].replace("-", ""),
        domain=props["Domain"]["select"]["name"],
        query=_plain_text(props["Query"]),
        pair_id=pair_id or None,
        lang="en",  # not yet a Notion column; defaulted at export
        web_search=props["Web search?"]["checkbox"],
        notes=_plain_text(props["Notes"]),
    )


def fetch_pages(data_source_id: str, api_key: str) -> list[dict]:
    pages: list[dict] = []
    cursor: str | None = None
    with httpx.Client(
        base_url=NOTION_API,
        headers={"Authorization": f"Bearer {api_key}", "Notion-Version": NOTION_VERSION},
        timeout=30,
    ) as client:
        while True:
            body: dict = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            resp = client.post(f"/data_sources/{data_source_id}/query", json=body)
            resp.raise_for_status()
            data = resp.json()
            pages.extend(data["results"])
            if not data.get("has_more"):
                return pages
            cursor = data["next_cursor"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-source-id", default=DEFAULT_DATA_SOURCE_ID)
    parser.add_argument("--out", type=Path, default=Path("prompts/bank.jsonl"))
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("NOTION_API_KEY")
    if not api_key:
        print("NOTION_API_KEY is not set", file=sys.stderr)
        return 1

    records = [_to_record(p) for p in fetch_pages(args.data_source_id, api_key)]
    records.sort(key=lambda r: r.id)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        for rec in records:
            f.write(rec.model_dump_json() + "\n")
    print(f"wrote {len(records)} records to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
