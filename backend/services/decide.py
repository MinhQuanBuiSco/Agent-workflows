from models import Extraction, Playbook, PositionView
from services.adjudicator import adjudicate
from services.citation import is_verbatim

ABSENT_RATIONALE = {
    "accept": "Not in the contract. On this playbook, absence is an accept.",
    "fallback": "Not in the contract. On this playbook, absence needs a counsel glance.",
    "reject": "Not in the contract. On this playbook, absence is a reject.",
}

UNGROUNDED_RATIONALE = (
    "The excerpt is not a verbatim span of the contract, so this position cannot be cleared."
)
UNGROUNDED_COMMENT = (
    "The quote could not be found in the contract. Read this position. No redline is proposed."
)


def decide_positions(
    playbook: Playbook,
    document: str,
    extraction: Extraction,
) -> list[PositionView]:
    if extraction.document_type != "nda":
        return []

    by_id = {item.id: item for item in extraction.positions}
    decided: list[PositionView] = []
    for spec in playbook.positions:
        extracted = by_id.get(spec.id)
        if extracted is None or not extracted.present:
            verdict = spec.if_absent
            decided.append(
                PositionView(
                    id=spec.id,
                    title=spec.title,
                    critical=spec.critical,
                    verdict=verdict,
                    model_verdict=verdict,
                    present=False,
                    excerpt=None,
                    citation_ok=None,
                    rationale=ABSENT_RATIONALE[verdict],
                    comment=None if verdict == "accept" else spec.fallback_comment.strip(),
                    fields={},
                )
            )
            continue

        excerpt = (extracted.excerpt or "").strip() or None
        grounded = is_verbatim(excerpt, document)
        if not grounded:
            decided.append(
                PositionView(
                    id=spec.id,
                    title=spec.title,
                    critical=spec.critical,
                    verdict="ungrounded",
                    model_verdict="ungrounded",
                    present=True,
                    excerpt=excerpt,
                    citation_ok=False,
                    rationale=UNGROUNDED_RATIONALE,
                    comment=UNGROUNDED_COMMENT,
                    fields=extracted.fields,
                )
            )
            continue

        verdict, rationale = adjudicate(spec.rule, extracted.fields)
        decided.append(
            PositionView(
                id=spec.id,
                title=spec.title,
                critical=spec.critical,
                verdict=verdict,  # type: ignore[arg-type]
                model_verdict=verdict,  # type: ignore[arg-type]
                present=True,
                excerpt=excerpt,
                citation_ok=True,
                rationale=rationale,
                comment=None if verdict == "accept" else spec.fallback_comment.strip(),
                fields=extracted.fields,
            )
        )
    return decided
