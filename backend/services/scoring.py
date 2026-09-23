"""Score one contract from an extraction. Shared by fixture review and eval."""

from models import EvalReport, EvalRow, Extraction, GoldLabel, PositionView
from services.decide import decide_positions
from services.playbook import load_playbook
from services.router import route_positions


def score_extraction(
    document: str,
    extraction: Extraction,
) -> tuple[str, list[str], list[PositionView]]:
    playbook = load_playbook()
    positions = decide_positions(playbook, document, extraction)
    route, reasons = route_positions(extraction.document_type, positions)
    return route, reasons, positions


def score_against_gold(
    gold: GoldLabel,
    document: str,
    extraction: Extraction,
) -> EvalRow:
    route, _reasons, positions = score_extraction(document, extraction)
    by_id = {position.id: position for position in positions}
    false_accepts = 0
    citation_failures = sum(1 for position in positions if position.verdict == "ungrounded")
    if gold.document_type == "nda":
        for position_id, expected in gold.positions.items():
            predicted = by_id[position_id].verdict
            if expected in {"fallback", "reject", "ungrounded"} and predicted == "accept":
                false_accepts += 1
    return EvalRow(
        id=gold.id,
        title=gold.title,
        gold_route=gold.route,
        predicted_route=route,  # type: ignore[arg-type]
        false_green=route == "green" and gold.route != "green",
        route_match=route == gold.route,
        citation_failures=citation_failures,
        false_accepts=false_accepts,
    )


def report_from_rows(mode: str, rows: list[EvalRow], gold_labels: list[GoldLabel]) -> EvalReport:
    false_accept_base = 0
    for gold in gold_labels:
        if gold.document_type != "nda":
            continue
        false_accept_base += sum(
            1
            for verdict in gold.positions.values()
            if verdict in {"fallback", "reject", "ungrounded"}
        )
    count = len(rows)
    false_green = sum(1 for row in rows if row.false_green)
    route_correct = sum(1 for row in rows if row.route_match)
    return EvalReport(
        mode=mode,  # type: ignore[arg-type]
        sample_count=count,
        false_green=false_green,
        false_green_rate=(false_green / count) if count else 0.0,
        route_correct=route_correct,
        route_accuracy=(route_correct / count) if count else 0.0,
        false_accept=sum(row.false_accepts for row in rows),
        false_accept_base=false_accept_base,
        citation_failures=sum(row.citation_failures for row in rows),
        rows=rows,
    )
