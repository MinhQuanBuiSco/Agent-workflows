import threading
import uuid
from datetime import UTC, datetime

from models import AuditEvent, DecisionIn, Matter, MatterSummary, PositionView
from services.corpus import load_gold, load_sample_text
from services.router import route_positions


class DecisionError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class Store:
    def __init__(self) -> None:
        self._matters: dict[str, Matter] = {}
        self._lock = threading.Lock()

    def clear(self) -> None:
        with self._lock:
            self._matters.clear()

    def create_from_sample(self, sample_id: str) -> Matter:
        gold = load_gold(sample_id)
        matter = self._new_matter(
            filename=f"{sample_id}.txt",
            sample_id=sample_id,
            title=gold.title,
            counterparty=gold.counterparty,
            text=load_sample_text(sample_id),
        )
        self._audit(matter, "playbook", "created", f"Opened sample {gold.title}.")
        self.save(matter)
        return matter

    def create_upload(self, filename: str, text: str) -> Matter:
        matter = self._new_matter(
            filename=filename,
            sample_id=None,
            title=filename,
            counterparty=None,
            text=text,
        )
        self._audit(matter, "playbook", "created", f"Uploaded {filename}.")
        self.save(matter)
        return matter

    def get(self, matter_id: str) -> Matter:
        with self._lock:
            try:
                matter = self._matters[matter_id]
            except KeyError as exc:
                raise KeyError(matter_id) from exc
            return matter.model_copy(deep=True)

    def save(self, matter: Matter) -> Matter:
        with self._lock:
            self._matters[matter.id] = matter.model_copy(deep=True)
        return matter

    def list_summaries(self) -> list[MatterSummary]:
        with self._lock:
            matters = list(self._matters.values())
        matters.sort(key=lambda item: item.created_at, reverse=True)
        return [MatterSummary.model_validate(item.model_dump()) for item in matters]

    def apply_decision(self, matter_id: str, decision: DecisionIn) -> Matter:
        matter = self.get(matter_id)
        if matter.status == "approved":
            raise DecisionError("This matter is already closed.", 409)
        if matter.status != "needs_review" or matter.route is None:
            raise DecisionError("Review the matter before recording a decision.")

        if decision.action == "override":
            if not decision.overrides:
                raise DecisionError("An override needs at least one position.")
            by_id = {position.id: position for position in matter.positions}
            for override in decision.overrides:
                note = override.note.strip()
                if len(note) < 3:
                    raise DecisionError("Each override needs a note.")
                try:
                    position = by_id[override.position_id]
                except KeyError as exc:
                    raise DecisionError(f"Unknown position {override.position_id}.") from exc
                position.verdict = override.verdict
                position.overridden = True
                position.human_note = note
                self._audit(
                    matter,
                    "counsel",
                    "overridden",
                    f"{position.title} set to {override.verdict}. {note}",
                )
            matter.route, matter.route_reasons = _reroute(matter)
            self._audit(
                matter,
                "playbook",
                "route_recomputed",
                f"Route is now {matter.route}. The model route stays {matter.model_route}.",
            )
            return self.save(matter)

        if decision.action == "approve":
            if matter.route != "green":
                raise DecisionError(
                    "Only a green route can be approved. Yellow, red, and out-of-playbook "
                    "matters use approve with exceptions, which does not turn the route green."
                )
            matter.status = "approved"
            matter.disposition = "approved"
            self._audit(matter, "counsel", "approved", "Approved on a green route.")
            return self.save(matter)

        note = decision.note.strip()
        if len(note) < 3:
            raise DecisionError("Approve with exceptions needs a note.")
        if matter.route == "green":
            raise DecisionError("A green route uses the approve action.")
        matter.status = "approved"
        matter.disposition = "approved_with_exceptions"
        self._audit(
            matter,
            "counsel",
            "approved_with_exceptions",
            f"Closed as {matter.route} with exceptions. {note}",
        )
        return self.save(matter)

    def _new_matter(
        self,
        filename: str,
        sample_id: str | None,
        title: str,
        counterparty: str | None,
        text: str,
    ) -> Matter:
        now = _now()
        return Matter(
            id=uuid.uuid4().hex[:8],
            filename=filename,
            sample_id=sample_id,
            title=title,
            counterparty=counterparty,
            status="new",
            text=text,
            created_at=now,
        )

    def record(self, matter: Matter, actor: str, kind: str, detail: str) -> None:
        self._audit(matter, actor, kind, detail)

    def _audit(self, matter: Matter, actor: str, kind: str, detail: str) -> None:
        matter.audit.append(
            AuditEvent(id=uuid.uuid4().hex[:8], at=_now(), actor=actor, kind=kind, detail=detail)
        )


def _reroute(matter: Matter) -> tuple[str, list[str]]:
    return route_positions(matter.document_type, matter.positions)


def _now() -> str:
    return datetime.now(UTC).isoformat()


store = Store()


def positions_for_route(matter: Matter) -> list[PositionView]:
    return matter.positions
