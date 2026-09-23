import pytest

from models import PositionView
from services.adjudicator import adjudicate
from services.router import route_positions


def _position(verdict: str, critical: bool = True, title: str = "Clause") -> PositionView:
    return PositionView(
        id=title.lower(),
        title=title,
        critical=critical,
        verdict=verdict,  # type: ignore[arg-type]
        model_verdict=verdict,  # type: ignore[arg-type]
        present=True,
        rationale="because the rule said so",
    )


def test_router_green_only_when_every_position_accepts():
    route, _ = route_positions(
        "nda",
        [_position("accept", True, "A"), _position("accept", False, "B")],
    )
    assert route == "green"


def test_router_critical_reject_is_red_and_beats_fallback():
    route, reasons = route_positions(
        "nda",
        [_position("reject", True, "Term"), _position("fallback", False, "Law")],
    )
    assert route == "red"
    assert any("Term" in reason for reason in reasons)
    assert all("Law" not in reason for reason in reasons)


def test_router_critical_ungrounded_is_red():
    positions = [_position("ungrounded", True)]
    route, _reasons = route_positions("nda", positions)
    assert route == "red"


def test_router_noncritical_reject_is_yellow():
    route, _ = route_positions(
        "nda",
        [_position("accept", True, "A"), _position("reject", False, "Return")],
    )
    assert route == "yellow"


def test_router_fallback_is_yellow():
    route, _ = route_positions("nda", [_position("fallback", True, "Term")])
    assert route == "yellow"


def test_router_other_document_is_not_scored_green():
    route, reasons = route_positions("other", [_position("accept")])
    assert route == "out_of_playbook"
    assert reasons


@pytest.mark.parametrize(
    ("rule", "fields", "expected"),
    [
        ("mutuality", {"mutual": True, "favors_us": False}, "accept"),
        ("mutuality", {"mutual": False, "favors_us": True}, "fallback"),
        ("mutuality", {"mutual": False, "favors_us": False}, "reject"),
        ("term", {"years": 3, "perpetual": False}, "accept"),
        ("term", {"years": 2, "perpetual": False}, "accept"),
        ("term", {"years": 5, "perpetual": False, "trade_secret_only": False}, "fallback"),
        ("term", {"years": 1, "perpetual": False}, "fallback"),
        ("term", {"years": None, "perpetual": True}, "reject"),
        ("term", {"years": 7, "perpetual": False}, "reject"),
        ("governing_law", {"jurisdiction": "Delaware"}, "accept"),
        ("governing_law", {"jurisdiction": "Texas"}, "fallback"),
        ("governing_law", {"jurisdiction": "England"}, "reject"),
        ("residuals", {"has_residual": False}, "accept"),
        ("residuals", {"has_residual": True}, "reject"),
        ("ai_training", {"grants_training": False}, "accept"),
        ("ai_training", {"grants_training": True}, "reject"),
        ("personal_data", {"excludes_personal_data": False, "requires_dpa": False}, "reject"),
        ("personal_data", {"excludes_personal_data": True, "requires_dpa": True}, "accept"),
        ("non_solicit", {"scope": "broad"}, "reject"),
        ("non_solicit", {"scope": "narrow"}, "fallback"),
        ("return_destroy", {"has_return_or_destroy": True, "archive_copy": True}, "fallback"),
        ("return_destroy", {"has_return_or_destroy": False, "archive_copy": False}, "reject"),
        ("compelled_notice", {"must_notify": False}, "reject"),
    ],
)
def test_rules(rule, fields, expected):
    verdict, rationale = adjudicate(rule, fields)
    assert verdict == expected
    assert rationale
