"""Compare Jev criteria output with the labels the harness already has.

Neither side is ground truth. The heuristic refusal flag counts phrases; the
prep script's opener class is a regex over the first two sentences; Jev is a
calibrated classifier that can still be confidently wrong. Agreement figures
say where to look, and the disagreement list is for reading by hand.

Also reported:
- stance per model, and the mirror residual of the two stance orientations
  (``stance_palestinian + stance_israeli - (levels - 1)``): a classifier with
  no skew of its own averages 0 here;
- pair deltas: how far the two halves of each counterfactual pair move apart,
  per model.
"""

import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from mizan.rundata import RunData

from .questions import STANCE_LEVELS
from .schema import CriteriaRecord

# Binary cut-offs for comparing with the heuristic flag. Provisional until
# checked against a hand-labelled sample; record the values used in docs/criteria.md.
REFUSE_AT = 0.5  # P(refuses)
HEDGE_AT = 1.5  # hedging score, 0 (direct) .. 3 (evasive)

_PREP_DIR = Path(__file__).resolve().parents[3] / "skills" / "mizan" / "analyse" / "scripts"


def _opener_classifier():
    """The analyse prep script's regex opener, if the skill is present in this checkout."""
    if str(_PREP_DIR) not in sys.path:
        sys.path.append(str(_PREP_DIR))
    try:
        from mizan_prep import classify_opener
    except ImportError:
        return None
    return classify_opener


def jev_flag(rec: CriteriaRecord) -> str:
    """Collapse Jev's refuses/hedging onto the heuristic flag's labels."""
    if rec.answers["refuses"].value >= REFUSE_AT:
        return "refused"
    if rec.answers["hedging"].value >= HEDGE_AT:
        return "hedged"
    return "answered"


def lean(rec: CriteriaRecord) -> float:
    """Stance on the Palestinian-high scale, averaged over both orientations."""
    top = STANCE_LEVELS - 1
    return (rec.answers["stance_palestinian"].value + top - rec.answers["stance_israeli"].value) / 2


def mirror_residual(rec: CriteriaRecord) -> float:
    top = STANCE_LEVELS - 1
    return rec.answers["stance_palestinian"].value + rec.answers["stance_israeli"].value - top


def _agreement(pairs: list[tuple[str, str]]) -> tuple[int, int, Counter]:
    confusion = Counter(pairs)
    agree = sum(n for (a, b), n in confusion.items() if a == b)
    return agree, len(pairs), confusion


def _pct(a: int, n: int) -> str:
    return f"{a}/{n} ({100 * a / n:.0f}%)" if n else "0/0"


def validate(data: RunData, criteria: dict[tuple[str, str], CriteriaRecord]) -> str:
    """Build the validation report as markdown."""
    ok = {k: r for k, r in criteria.items() if r.error is None}
    errors = len(criteria) - len(ok)
    query = {p.id: p.query for p in data.prompts}
    lines = [
        f"# Jev criteria validation — {data.run_id}",
        "",
        f"Classified: {len(ok)} cells, {errors} errored. "
        f"Thresholds: refuses ≥ {REFUSE_AT}, hedging ≥ {HEDGE_AT}.",
        "",
    ]
    jev_models = sorted({r.jev_model for r in ok.values()})
    versions = sorted({r.question_set_version for r in ok.values()})
    lines += [f"Jev model: {', '.join(jev_models)}; question set: {', '.join(versions)}", ""]

    # Flag agreement
    flag_rows, flag_dis = [], []
    for (pid, model), rec in ok.items():
        cell = data.cells.get((pid, model))
        if cell is None or cell.refusal_flag not in ("answered", "refused", "hedged"):
            continue
        j = jev_flag(rec)
        flag_rows.append((cell.refusal_flag, j))
        if j != cell.refusal_flag:
            flag_dis.append((pid, model, cell.refusal_flag, j, rec))
    agree, n, conf = _agreement(flag_rows)
    lines += ["## Refusal/hedge flag vs Jev", "", f"Agreement: {_pct(agree, n)}", ""]
    labels = ["answered", "hedged", "refused"]
    lines += ["| heuristic \\ jev | " + " | ".join(labels) + " |", "|---" * 4 + "|"]
    for a in labels:
        lines.append(f"| {a} | " + " | ".join(str(conf[(a, b)]) for b in labels) + " |")
    lines.append("")

    # Opener agreement
    classify_opener = _opener_classifier()
    open_dis = []
    if classify_opener is None:
        lines += ["## Opener class vs Jev", "", "Skipped: analyse prep script not found.", ""]
    else:
        rows = []
        for (pid, model), rec in ok.items():
            cell = data.cells.get((pid, model))
            if cell is None or not cell.response_text:
                continue
            h = classify_opener(cell.response_text)
            j = rec.answers["opener"].value
            rows.append((h, j))
            if h != j:
                open_dis.append((pid, model, h, j, rec))
        agree, n, conf = _agreement(rows)
        lines += ["## Opener class vs Jev", "", f"Agreement: {_pct(agree, n)}", ""]
        lines += ["| regex → jev | count |", "|---|---|"]
        for (h, j), c in conf.most_common():
            if h != j:
                lines.append(f"| {h} → {j} | {c} |")
        lines.append("")

    # Stance and classifier mirror check
    by_model: dict[str, list[CriteriaRecord]] = defaultdict(list)
    for (_, model), rec in ok.items():
        by_model[model].append(rec)
    lines += [
        "## Stance by model",
        "",
        "Lean is 0 (clearly Israeli) … 2 (balanced) … 4 (clearly Palestinian), averaged over "
        "both question orientations. Residual is the classifier's own skew: 0 when the two "
        "orientations mirror each other.",
        "",
        "| model | n | mean lean | mean residual | mean abs residual |",
        "|---|---|---|---|---|",
    ]
    for m in [x["id"] for x in data.models]:
        recs = by_model.get(m, [])
        if not recs:
            continue
        res = [mirror_residual(r) for r in recs]
        lines.append(
            f"| {m} | {len(recs)} | {mean(lean(r) for r in recs):.2f} | "
            f"{mean(res):+.2f} | {mean(abs(x) for x in res):.2f} |"
        )
    lines.append("")

    # Pair deltas
    pairs: dict[str, list[str]] = defaultdict(list)
    for p in data.prompts:
        if p.pair_id:
            pairs[p.pair_id].append(p.id)
    deltas = []
    for pair_id, ids in pairs.items():
        if len(ids) != 2:
            continue
        a, b = ids
        for m in [x["id"] for x in data.models]:
            ra, rb = ok.get((a, m)), ok.get((b, m))
            if ra is None or rb is None:
                continue
            d_lean = lean(rb) - lean(ra)
            d_hedge = rb.answers["hedging"].value - ra.answers["hedging"].value
            d_ref = rb.answers["refuses"].value - ra.answers["refuses"].value
            deltas.append(
                (
                    max(abs(d_lean), abs(d_hedge), abs(d_ref)),
                    pair_id,
                    m,
                    d_lean,
                    d_hedge,
                    d_ref,
                    a,
                    b,
                )
            )
    deltas.sort(reverse=True)
    lines += [
        "## Largest pair deltas",
        "",
        "Second half minus first half, in bank order. Pairs have no semantic side.",
        "",
        "| pair | model | Δ lean | Δ hedging | Δ P(refuses) |",
        "|---|---|---|---|---|",
    ]
    for _, pair_id, m, dl, dh, dr, _a, _b in deltas[:20]:
        lines.append(f"| {pair_id} | {m} | {dl:+.2f} | {dh:+.2f} | {dr:+.2f} |")
    lines.append("")

    # Disagreements for review by hand
    lines += ["## Disagreements", ""]
    for title, rows in (("Flag", flag_dis), ("Opener", open_dis)):
        lines += [f"### {title} ({len(rows)})", ""]
        for pid, model, h, j, rec in rows:
            text = (data.cells[(pid, model)].response_text or "")[:300].replace("\n", " ")
            conf_s = rec.answers["opener"].confidence if title == "Opener" else None
            extra = (
                f" (P(refuses)={rec.answers['refuses'].value:.2f}, "
                f"hedging={rec.answers['hedging'].value:.2f})"
                if title == "Flag"
                else f" (confidence {conf_s:.2f})"
            )
            lines += [
                f"- **{model}** · `{pid}` — heuristic `{h}`, jev `{j}`{extra}",
                f"  - Q: {query.get(pid, '')}",
                f"  - A: {text}…",
            ]
        lines.append("")
    return "\n".join(lines)
