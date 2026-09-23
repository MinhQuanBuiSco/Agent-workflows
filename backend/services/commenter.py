from models import Playbook, PositionView
from services.json_text import parse_json_object
from services.llm import Delta, complete
from services.playbook import render_comment_prompt

SYSTEM = (
    "You draft short redline comments for a lawyer. Keep the playbook's negotiating "
    "position. Reply with JSON only."
)


async def draft_comments(
    playbook: Playbook,
    positions: list[PositionView],
    on_delta: Delta | None = None,
) -> dict[str, str]:
    """One call for every fallback or reject. Ungrounded positions are not sent.

    If the model reply is unusable, the playbook's own fallback sentence is the comment.
    A failed prose call must not fail the review or change the route.
    """
    specs = {position.id: position for position in playbook.positions}
    pending = [
        position
        for position in positions
        if position.verdict in {"fallback", "reject"} and position.comment
    ]
    if not pending:
        return {}

    items = []
    for position in pending:
        spec = specs[position.id]
        items.append(
            {
                "id": position.id,
                "verdict": position.verdict,
                "rationale": position.rationale,
                "fallback_comment": spec.fallback_comment.strip(),
                "excerpt": position.excerpt,
            }
        )
    try:
        raw = await complete(
            SYSTEM,
            render_comment_prompt(items),
            temperature=0.2,
            max_tokens=1200,
            on_delta=on_delta,
        )
        parsed = parse_json_object(raw)
        comments = parsed.get("comments", [])
        found: dict[str, str] = {}
        if isinstance(comments, list):
            for item in comments:
                comment = item.get("comment") if isinstance(item, dict) else None
                position_id = item.get("id") if isinstance(item, dict) else None
                if isinstance(comment, str) and position_id:
                    text = comment.strip()
                    if text:
                        found[str(position_id)] = text
        return found
    except Exception:
        return {}
