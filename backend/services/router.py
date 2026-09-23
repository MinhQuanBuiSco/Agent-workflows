from models import PositionView

Route = str


def route_positions(
    document_type: str | None,
    positions: list[PositionView],
) -> tuple[Route, list[str]]:
    """The model never assigns this. Critical reject or ungrounded blocks green."""
    if document_type != "nda":
        return (
            "out_of_playbook",
            ["This document is not an NDA. The Acme NDA playbook does not score it."],
        )

    reds: list[str] = []
    yellows: list[str] = []
    for position in positions:
        line = f"{position.title}: {position.verdict}. {position.rationale}"
        if position.verdict in {"reject", "ungrounded"} and position.critical:
            reds.append(line)
        elif position.verdict == "fallback":
            yellows.append(line)
        elif position.verdict in {"reject", "ungrounded"}:
            yellows.append(line)
        elif position.verdict != "accept":
            yellows.append(line)

    if reds:
        return "red", reds
    if yellows:
        return "yellow", yellows
    return "green", ["Every playbook position is an accept, and every quote is in the contract."]
