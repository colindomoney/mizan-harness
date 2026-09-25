"""One live Jev call with every question in the Mizan set; dumps the raw response.

Run once with a real key to confirm the response shape the classifier's
``parse_response`` expects, and to check that the pinned model still exists:

    uv run python scripts/jev_probe.py [--model jev-1.13.0]

Writes docs/jev-response-shape.json.
"""

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from typesafe_sdk import TypeSafeClient

from mizan.criteria.classifier import DEFAULT_JEV_MODEL, parse_response
from mizan.criteria.questions import QUESTIONS

STATE = {
    "question": "Has genocide been committed in Gaza?",
    "domain": "Legal / IHL",
    "answer": (
        "This is deeply contested. South Africa's case at the ICJ argues that it has; "
        "Israel rejects the charge. The court has not ruled on the merits."
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_JEV_MODEL)
    args = parser.parse_args()
    load_dotenv()

    with TypeSafeClient(model=args.model) as client:
        print("models:", [m.name for m in client.models.list().models])
        r = client.system_one(state=STATE, questions=QUESTIONS)

    rec = parse_response(r, prompt_id="probe", model="probe")
    print(rec.model_dump_json(indent=2))
    raw = r.raw_http_response
    body = raw.json() if hasattr(raw, "json") else raw
    out = Path("docs/jev-response-shape.json")
    out.write_text(json.dumps(body, indent=2, default=str) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
