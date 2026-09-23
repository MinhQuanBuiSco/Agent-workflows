from typing import Any, Literal

from pydantic import BaseModel, Field

Verdict = Literal["accept", "fallback", "reject", "ungrounded"]
RouteName = Literal["green", "yellow", "red", "out_of_playbook"]
MatterStatus = Literal["new", "running", "needs_review", "approved"]
Disposition = Literal["approved", "approved_with_exceptions"]


class FieldSpec(BaseModel):
    name: str
    type: str
    description: str


class PlaybookPosition(BaseModel):
    id: str
    title: str
    critical: bool
    if_absent: Literal["accept", "fallback", "reject"]
    rule: str
    requirement: str
    fallback_comment: str
    fields: list[FieldSpec]


class Playbook(BaseModel):
    id: str
    name: str
    company: str
    positions: list[PlaybookPosition]


class ExtractedPosition(BaseModel):
    id: str
    present: bool
    excerpt: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "ignore"}


class Extraction(BaseModel):
    document_type: Literal["nda", "other"]
    counterparty: str | None = None
    positions: list[ExtractedPosition] = Field(default_factory=list)

    model_config = {"extra": "ignore"}


class PositionView(BaseModel):
    id: str
    title: str
    critical: bool
    verdict: Verdict
    model_verdict: Verdict
    present: bool
    excerpt: str | None = None
    citation_ok: bool | None = None
    rationale: str
    comment: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    overridden: bool = False
    human_note: str | None = None


class AuditEvent(BaseModel):
    id: str
    at: str
    actor: str
    kind: str
    detail: str


class Matter(BaseModel):
    id: str
    filename: str
    sample_id: str | None = None
    title: str
    counterparty: str | None = None
    status: MatterStatus
    document_type: str | None = None
    route: RouteName | None = None
    model_route: RouteName | None = None
    route_reasons: list[str] = Field(default_factory=list)
    disposition: Disposition | None = None
    positions: list[PositionView] = Field(default_factory=list)
    text: str
    audit: list[AuditEvent] = Field(default_factory=list)
    created_at: str


class MatterSummary(BaseModel):
    id: str
    filename: str
    sample_id: str | None = None
    title: str
    counterparty: str | None = None
    status: MatterStatus
    document_type: str | None = None
    route: RouteName | None = None
    model_route: RouteName | None = None
    disposition: Disposition | None = None
    created_at: str


class GoldLabel(BaseModel):
    id: str
    title: str
    counterparty: str
    summary: str
    document_type: Literal["nda", "other"]
    route: RouteName
    positions: dict[str, Verdict] = Field(default_factory=dict)


class OverrideIn(BaseModel):
    position_id: str
    verdict: Literal["accept", "fallback", "reject"]
    note: str = Field(min_length=3)


class DecisionIn(BaseModel):
    action: Literal["override", "approve", "approve_with_exceptions"]
    overrides: list[OverrideIn] = Field(default_factory=list)
    note: str = ""


class HealthResponse(BaseModel):
    status: str
    version: str


class EvalRow(BaseModel):
    id: str
    title: str
    gold_route: RouteName
    predicted_route: RouteName
    false_green: bool
    route_match: bool
    citation_failures: int
    false_accepts: int


class EvalReport(BaseModel):
    mode: Literal["fixture", "live"]
    sample_count: int
    false_green: int
    false_green_rate: float
    route_correct: int
    route_accuracy: float
    false_accept: int
    false_accept_base: int
    citation_failures: int
    rows: list[EvalRow]
    error: str | None = None
