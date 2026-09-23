import asyncio
import json
import os
import time
from collections import Counter

from config import LLM_MODEL
from models import Extraction, Matter, PositionView
from services.commenter import draft_comments
from services.corpus import load_fixture
from services.decide import decide_positions
from services.extractor import extract_contract
from services.playbook import load_playbook
from services.router import route_positions
from services.store import store
from services.trace import Run

# Fixture mode replays the recorded extraction as if it were streaming, so the
# desk can demo the trace with the model off. It is labeled a replay.
REPLAY_SECONDS = float(os.environ.get("TRACE_REPLAY_SECONDS", "3"))
REPLAY_CHUNK = 24


class ReviewError(Exception):
    pass


async def run_review(matter_id: str, mode: str, run: Run) -> Matter:
    matter = store.get(matter_id)
    if matter.status == "approved":
        raise ReviewError("This matter is already closed.")
    if mode not in {"fixture", "live"}:
        raise ReviewError("mode must be fixture or live.")

    matter.status = "running"
    store.record(matter, "playbook", "review_started", f"Review started in {mode} mode.")
    store.save(matter)
    playbook = load_playbook()
    run.emit(
        "run_started",
        mode=mode,
        model=LLM_MODEL if mode == "live" else "recorded extraction",
        positions=[
            {"id": spec.id, "title": spec.title, "critical": spec.critical, "rule": spec.rule}
            for spec in playbook.positions
        ],
    )

    try:
        started = time.perf_counter()
        _stage(run, "parsing", "python", "running", "Reading the contract text.")
        words = len(matter.text.split())
        _stage(
            run,
            "parsing",
            "python",
            "done",
            f"{words:,} words, {len(matter.text):,} characters.",
            ms=_ms(started),
        )

        extraction = await _extract(matter, mode, run)
        run.emit(
            "document",
            document_type=extraction.document_type,
            counterparty=extraction.counterparty,
        )

        started = time.perf_counter()
        _stage(
            run,
            "verifying",
            "python",
            "running",
            "Checking that every quote is a span of the contract.",
        )
        positions = decide_positions(playbook, matter.text, extraction)
        specs = {spec.id: spec for spec in playbook.positions}
        for position in positions:
            run.emit(
                "citation",
                position=position.id,
                title=position.title,
                present=position.present,
                excerpt=position.excerpt,
                found=position.citation_ok,
            )
        grounded = sum(1 for p in positions if p.citation_ok)
        failed = sum(1 for p in positions if p.citation_ok is False)
        _stage(
            run,
            "verifying",
            "python",
            "done",
            _gate_summary(extraction, grounded, failed),
            ms=_ms(started),
        )

        started = time.perf_counter()
        _stage(
            run,
            "adjudicating",
            "python",
            "running",
            "Applying playbook rules. The model does not assign the verdict.",
        )
        for position in positions:
            run.emit(
                "rule",
                position=position.id,
                title=position.title,
                rule=specs[position.id].rule if position.citation_ok else None,
                basis=_basis(position),
                fields=position.fields,
                verdict=position.verdict,
                rationale=position.rationale,
                critical=position.critical,
            )
        _stage(
            run,
            "adjudicating",
            "python",
            "done",
            f"{len(positions)} rules applied." if positions else "Not an NDA. No rule applies.",
            ms=_ms(started),
        )

        await _draft(run, mode, extraction, positions)

        started = time.perf_counter()
        _stage(
            run, "routing", "python", "running", "Computing green, yellow, red, or out of playbook."
        )
        route, reasons = route_positions(extraction.document_type, positions)
        tally = Counter(position.verdict for position in positions)
        run.emit("route", route=route, reasons=reasons, tally=dict(tally))
        _stage(run, "routing", "python", "done", f"Route is {route}.", ms=_ms(started))

        matter.document_type = extraction.document_type
        if extraction.counterparty:
            matter.counterparty = extraction.counterparty
        matter.positions = positions
        matter.route = route  # type: ignore[assignment]
        matter.model_route = route  # type: ignore[assignment]
        matter.route_reasons = reasons
        matter.disposition = None
        matter.status = "needs_review"
        for position in positions:
            if position.verdict == "ungrounded":
                store.record(
                    matter,
                    "playbook",
                    "citation_failed",
                    f"{position.title}: the quote is not in the contract.",
                )
        store.record(
            matter,
            "playbook",
            "review_completed",
            f"Model route is {route}. This value stays put if counsel overrides a verdict.",
        )
        return store.save(matter)
    except BaseException as exc:
        # BaseException, so a cancelled task does not leave the matter stuck on running.
        failed = store.get(matter_id)
        failed.status = "needs_review" if failed.model_route else "new"
        detail = (
            "The review was cancelled." if isinstance(exc, asyncio.CancelledError) else str(exc)
        )
        store.record(failed, "playbook", "review_failed", detail)
        store.save(failed)
        raise


async def _extract(matter: Matter, mode: str, run: Run) -> Extraction:
    if mode == "fixture":
        if not matter.sample_id:
            raise ReviewError("Fixture mode only replays built-in samples. Uploads need live mode.")
        try:
            extraction = load_fixture(matter.sample_id)
        except FileNotFoundError as exc:
            raise ReviewError(f"No recorded extraction for {matter.sample_id}.") from exc
        _stage(
            run,
            "extracting",
            "model",
            "running",
            "Replaying a recorded extraction. The model is not being called.",
        )
        started = time.perf_counter()
        run.emit("model_call", call="extract", status="start", replay=True, prompt_chars=None)
        text = json.dumps(extraction.model_dump(), indent=2)
        chunks = [text[i : i + REPLAY_CHUNK] for i in range(0, len(text), REPLAY_CHUNK)]
        pause = REPLAY_SECONDS / max(len(chunks), 1)
        for chunk in chunks:
            await run.delta("extract", chunk)
            if pause:
                await asyncio.sleep(pause)
        run.emit(
            "model_call", call="extract", status="end", replay=True, tokens=None, ms=_ms(started)
        )
        _stage(run, "extracting", "model", "done", "Recorded extraction replayed.", ms=_ms(started))
        return extraction

    playbook = load_playbook()
    _stage(
        run,
        "extracting",
        "model",
        "running",
        "Asking the local model for verbatim excerpts and structured fields.",
    )
    started = time.perf_counter()
    tokens = 0

    async def on_delta(text: str) -> None:
        nonlocal tokens
        tokens += 1
        await run.delta("extract", text)

    async def on_retry(error: str) -> None:
        run.emit("model_retry", call="extract", error=error)

    run.emit(
        "model_call",
        call="extract",
        status="start",
        replay=False,
        prompt_chars=len(matter.text),
    )
    extraction = await extract_contract(playbook, matter.text, on_delta=on_delta, on_retry=on_retry)
    run.emit(
        "model_call", call="extract", status="end", replay=False, tokens=tokens, ms=_ms(started)
    )
    _stage(
        run,
        "extracting",
        "model",
        "done",
        f"{len(extraction.positions)} positions extracted.",
        ms=_ms(started),
    )
    return extraction


async def _draft(
    run: Run, mode: str, extraction: Extraction, positions: list[PositionView]
) -> None:
    needs_comment = [p for p in positions if p.verdict in {"fallback", "reject"} and p.comment]
    if mode != "live" or extraction.document_type != "nda" or not needs_comment:
        reason = (
            "Fixture mode uses the playbook's own sentences."
            if mode != "live"
            else "Nothing to redline."
        )
        _stage(run, "drafting", "model", "skipped", reason)
        for position in needs_comment:
            run.emit(
                "comment",
                position=position.id,
                title=position.title,
                text=position.comment,
                source="playbook",
            )
        return

    _stage(
        run,
        "drafting",
        "model",
        "running",
        f"Phrasing {len(needs_comment)} redline comments. The route cannot change here.",
    )
    started = time.perf_counter()
    tokens = 0

    async def on_delta(text: str) -> None:
        nonlocal tokens
        tokens += 1
        await run.delta("draft", text)

    run.emit("model_call", call="draft", status="start", replay=False, prompt_chars=None)
    drafted = await draft_comments(load_playbook(), positions, on_delta=on_delta)
    run.emit("model_call", call="draft", status="end", replay=False, tokens=tokens, ms=_ms(started))
    for position in positions:
        if position.id in drafted:
            position.comment = drafted[position.id]
    for position in needs_comment:
        source = "model" if position.id in drafted else "playbook"
        run.emit(
            "comment",
            position=position.id,
            title=position.title,
            text=position.comment,
            source=source,
        )
    _stage(
        run,
        "drafting",
        "model",
        "done",
        f"{len(drafted)} of {len(needs_comment)} comments drafted by the model.",
        ms=_ms(started),
    )


def _stage(
    run: Run, step: str, lane: str, status: str, message: str, ms: int | None = None
) -> None:
    run.emit("progress", step=step, lane=lane, status=status, message=message, ms=ms)


def _basis(position: PositionView) -> str:
    if not position.present:
        return "absent"
    if position.citation_ok is False:
        return "ungrounded"
    return "rule"


def _gate_summary(extraction: Extraction, grounded: int, failed: int) -> str:
    if extraction.document_type != "nda":
        return "Not an NDA. No quotes to check."
    if failed:
        return f"{grounded} quotes found verbatim. {failed} not in the contract."
    return f"{grounded} quotes found verbatim in the contract."


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
