import json

import pytest
from fastapi.testclient import TestClient

from app import app
from services import evals, llm, review
from services.store import store
from services.trace import hub


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(review, "REPLAY_SECONDS", 0)
    store.clear()
    hub.clear()
    evals.clear_reports()
    llm.reset_client()
    yield
    store.clear()
    hub.clear()
    evals.clear_reports()


@pytest.fixture
def client():
    return TestClient(app)


def _events(client: TestClient, matter_id: str, mode: str = "fixture") -> list[dict]:
    with client.stream(
        "POST",
        f"/api/matters/{matter_id}/review",
        params={"mode": mode},
    ) as response:
        assert response.status_code == 200, response.read()
        body = response.read().decode()
    return _logged(body)


def _logged(body: str) -> list[dict]:
    """Parse an SSE body. The first frame is the unlogged clock; drop it."""
    frames = [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]
    assert frames[0]["type"] == "clock"
    return frames[1:]


def _replay(client: TestClient, matter_id: str, after: int = -1) -> list[dict]:
    response = client.get(f"/api/matters/{matter_id}/events", params={"after": after})
    assert response.status_code == 200, response.text
    return _logged(response.text)


def test_sample_list_does_not_include_the_answer_key(client: TestClient):
    response = client.get("/api/samples")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 8
    assert "route" not in body[0]
    assert "positions" not in body[0]
    assert body[0]["counterparty"]


def test_fixture_review_streams_a_green_result(client: TestClient):
    created = client.post("/api/matters/sample/nda-clean-mutual")
    assert created.status_code == 200
    matter_id = created.json()["id"]

    events = _events(client, matter_id)
    steps = [event["step"] for event in events if event["type"] == "progress"]
    assert steps[0] == "parsing"
    assert "routing" in steps
    result = next(event for event in events if event["type"] == "result")
    assert result["data"]["route"] == "green"
    assert result["data"]["model_route"] == "green"
    assert result["data"]["status"] == "needs_review"

    approved = client.post(
        f"/api/matters/{matter_id}/decision",
        json={"action": "approve"},
    )
    assert approved.status_code == 200
    assert approved.json()["disposition"] == "approved"
    assert approved.json()["route"] == "green"


def test_red_cannot_be_approved_into_green(client: TestClient):
    created = client.post("/api/matters/sample/nda-perpetual").json()
    matter_id = created["id"]
    _events(client, matter_id)
    blocked = client.post(f"/api/matters/{matter_id}/decision", json={"action": "approve"})
    assert blocked.status_code == 400

    closed = client.post(
        f"/api/matters/{matter_id}/decision",
        json={"action": "approve_with_exceptions", "note": "Counsel will renegotiate the term."},
    )
    assert closed.status_code == 200
    body = closed.json()
    assert body["route"] == "red"
    assert body["model_route"] == "red"
    assert body["disposition"] == "approved_with_exceptions"
    assert any(event["kind"] == "approved_with_exceptions" for event in body["audit"])


def test_override_recomputes_route_but_not_the_model_route_or_eval(client: TestClient):
    created = client.post("/api/matters/sample/nda-perpetual").json()
    matter_id = created["id"]
    _events(client, matter_id)

    overridden = client.post(
        f"/api/matters/{matter_id}/decision",
        json={
            "action": "override",
            "overrides": [
                {
                    "position_id": "term",
                    "verdict": "accept",
                    "note": "Business accepted a perpetual term for this supplier.",
                }
            ],
        },
    )
    assert overridden.status_code == 200
    body = overridden.json()
    assert body["route"] == "green"
    assert body["model_route"] == "red"
    term = next(position for position in body["positions"] if position["id"] == "term")
    assert term["verdict"] == "accept"
    assert term["model_verdict"] == "reject"
    assert term["overridden"] is True

    report = client.get("/api/evals")
    assert report.status_code == 200
    fixture = report.json()["fixture"]
    assert fixture["false_green"] == 0
    assert fixture["route_correct"] == 8
    assert fixture["sample_count"] == 8
    perpetual = next(row for row in fixture["rows"] if row["id"] == "nda-perpetual")
    assert perpetual["predicted_route"] == "red"
    assert perpetual["false_green"] is False


def test_live_mode_does_not_fall_back_to_fixtures(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def offline():
        return {
            "reachable": False,
            "base_url": "http://127.0.0.1:8080/v1",
            "model": "test",
            "served_models": [],
            "detail": "connection refused",
        }

    monkeypatch.setattr(llm, "ping", offline)
    created = client.post("/api/matters/sample/nda-clean-mutual").json()
    response = client.post(f"/api/matters/{created['id']}/review", params={"mode": "live"})
    assert response.status_code == 503
    assert "not reachable" in response.json()["detail"].lower()
    matter = client.get(f"/api/matters/{created['id']}").json()
    assert matter["route"] is None
    assert matter["status"] == "new"


def test_upload_cannot_use_fixture_mode(client: TestClient):
    response = client.post(
        "/api/matters",
        files={"file": ("vendor.txt", b"This is a plain text contract.", "text/plain")},
    )
    assert response.status_code == 200
    matter_id = response.json()["id"]
    review = client.post(f"/api/matters/{matter_id}/review", params={"mode": "fixture"})
    assert review.status_code == 400
    assert "live" in review.json()["detail"].lower()


def test_trace_shows_the_model_and_python_steps_apart(client: TestClient):
    matter_id = client.post("/api/matters/sample/nda-perpetual").json()["id"]
    events = _events(client, matter_id)
    kinds = [event["type"] for event in events]

    assert kinds[0] == "run_started"
    assert kinds[-1] == "result"
    assert [event["seq"] for event in events] == list(range(len(events)))
    lanes = {event["step"]: event["lane"] for event in events if event["type"] == "progress"}
    assert lanes["extracting"] == "model"
    assert lanes["adjudicating"] == "python"
    assert lanes["routing"] == "python"

    streamed = "".join(event["text"] for event in events if event["type"] == "model_delta")
    assert json.loads(streamed)["document_type"] == "nda"
    starts = [
        event for event in events if event["type"] == "model_call" and event["status"] == "start"
    ]
    assert starts and all(event["replay"] for event in starts)

    citations = [event for event in events if event["type"] == "citation"]
    rules = [event for event in events if event["type"] == "rule"]
    assert len(citations) == len(rules) == 10
    term = next(event for event in rules if event["position"] == "term")
    assert term["verdict"] == "reject"
    assert term["rule"] == "term"
    route = next(event for event in events if event["type"] == "route")
    assert route["route"] == "red"
    assert kinds.index("rule") < kinds.index("route")


def test_trace_can_be_replayed_after_the_stream_closes(client: TestClient):
    matter_id = client.post("/api/matters/sample/nda-clean-mutual").json()["id"]
    assert client.get(f"/api/matters/{matter_id}/events").status_code == 404

    live = _events(client, matter_id)
    replayed = _replay(client, matter_id)
    assert replayed == live
    tail = _replay(client, matter_id, after=live[-3]["seq"])
    assert tail == live[-2:]


def test_demo_pdf_opens_as_an_upload(client: TestClient):
    created = client.post("/api/matters/demo")
    assert created.status_code == 200
    matter = created.json()
    assert matter["sample_id"] is None
    assert matter["filename"] == "Bluefin-Analytics-NDA.pdf"
    assert "Bluefin Analytics" in matter["text"]
    assert "survive for four (4) years" in matter["text"]

    review = client.post(f"/api/matters/{matter['id']}/review", params={"mode": "fixture"})
    assert review.status_code == 400

    pdf = client.get("/api/demo.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
