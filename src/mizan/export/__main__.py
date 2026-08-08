"""CLI: export a run dir to an Excel workbook and (optionally) Notion.

Usage:
    uv run python -m mizan.export runs/<timestamp>                # xlsx only
    uv run python -m mizan.export runs/<timestamp> --notion       # xlsx + Notion
    uv run python -m mizan.export --init-notion --parent-page-id <id>
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from mizan.rundata import load_run

from .notion import NotionExportError, create_runs_database, make_client, push_run
from .xlsx import write_workbook

DATA_SOURCE_ENV = "NOTION_RUNS_DATA_SOURCE_ID"


def _progress(pushed: int, total: int) -> None:
    print(f"\r  notion: {pushed}/{total} pages", end="", file=sys.stderr, flush=True)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a run dir to Excel and/or Notion.")
    parser.add_argument("run_dir", type=Path, nargs="?", help="runs/<timestamp> directory")
    parser.add_argument("--bank", type=Path, default=None, help="override bank snapshot path")
    parser.add_argument(
        "--xlsx", type=Path, default=None, help="workbook path (default: <run>/export.xlsx)"
    )
    parser.add_argument("--notion", action="store_true", help="also push the run to Notion")
    parser.add_argument(
        "--force", action="store_true", help="replace pages already pushed for this run"
    )
    parser.add_argument(
        "--data-source-id", default=None, help=f"override ${DATA_SOURCE_ENV} from .env"
    )
    parser.add_argument(
        "--init-notion", action="store_true", help="create the master Notion runs database"
    )
    parser.add_argument(
        "--parent-page-id", default=None, help="Notion page to create the database under"
    )
    parser.add_argument("--quiet", action="store_true", help="suppress progress output")
    args = parser.parse_args(argv)

    load_dotenv()

    if args.init_notion:
        if not args.parent_page_id:
            print("--init-notion requires --parent-page-id", file=sys.stderr)
            return 1
        api_key = os.environ.get("NOTION_API_KEY")
        if not api_key:
            print("NOTION_API_KEY is not set", file=sys.stderr)
            return 1
        with make_client(api_key) as client:
            data_source_id = create_runs_database(client=client, parent_page_id=args.parent_page_id)
        print(f"created 'Mizan runs' database — add to .env:\n{DATA_SOURCE_ENV}={data_source_id}")
        return 0

    if args.run_dir is None:
        parser.error("run_dir is required unless --init-notion")

    data = load_run(args.run_dir, bank_path=args.bank)
    if not data.bank_hash_matches:
        print("warning: bank snapshot ≠ manifest hash", file=sys.stderr)

    out = write_workbook(data, args.xlsx or args.run_dir / "export.xlsx")
    print(f"wrote {out}")

    if args.notion:
        api_key = os.environ.get("NOTION_API_KEY")
        if not api_key:
            print("NOTION_API_KEY is not set", file=sys.stderr)
            return 1
        data_source_id = args.data_source_id or os.environ.get(DATA_SOURCE_ENV)
        if not data_source_id:
            print(
                f"{DATA_SOURCE_ENV} is not set — run --init-notion first",
                file=sys.stderr,
            )
            return 1
        try:
            with make_client(api_key) as client:
                pushed = push_run(
                    data,
                    client=client,
                    data_source_id=data_source_id,
                    force=args.force,
                    on_progress=None if args.quiet else _progress,
                )
        except NotionExportError as exc:
            print(f"\nnotion: {exc}", file=sys.stderr)
            return 1
        if not args.quiet:
            print(file=sys.stderr)
        print(f"pushed {pushed} pages to Notion (run {data.run_id})")

    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
