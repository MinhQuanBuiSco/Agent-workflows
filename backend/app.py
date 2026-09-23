import json
import logging
import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from config import APP_VERSION, DEMO_PDF, MAX_FILE_SIZE_MB, UPLOADS_DIR, cors_origins
from models import DecisionIn, EvalReport, HealthResponse, Matter, MatterSummary, Playbook
from services import evals, llm
from services.corpus import list_gold
from services.parser import text_from_upload
from services.playbook import load_playbook
from services.review import run_review
from services.store import DecisionError, store
from services.trace import Run
from services.trace import hub as trace_hub

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Playbook Review",
    version=APP_VERSION,
    description="NDA playbook review. The model extracts quotes. Python decides the route.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


class EvalBundle(BaseModel):
    fixture: EvalReport
    live: EvalReport | None


def _matter_or_404(matter_id: str) -> Matter:
    try:
        return store.get(matter_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Matter not found.") from exc


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="healthy", version=APP_VERSION)


@app.get("/api/llm")
async def llm_status() -> dict:
    return await llm.ping()


@app.get("/api/playbook", response_model=Playbook)
async def playbook() -> Playbook:
    return load_playbook()


@app.get("/api/samples")
async def samples() -> list[dict]:
    # Gold routes stay on the eval endpoint. The queue should not ship the answer key.
    hidden = {"route", "positions"}
    return [
        {key: value for key, value in label.model_dump().items() if key not in hidden}
        for label in list_gold()
    ]


@app.get("/api/matters", response_model=list[MatterSummary])
async def list_matters() -> list[MatterSummary]:
    return store.list_summaries()


@app.post("/api/matters", response_model=Matter)
async def upload_matter(file: UploadFile = File(...)) -> Matter:
    payload = await file.read()
    if len(payload) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File is larger than {MAX_FILE_SIZE_MB} MB.")
    filename = file.filename or "upload.txt"
    try:
        text = text_from_upload(filename, payload)
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="TXT files must be UTF-8.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not text.strip():
        raise HTTPException(status_code=400, detail="No text found in that file.")
    return store.create_upload(filename, text)


@app.post("/api/matters/demo", response_model=Matter)
async def open_demo() -> Matter:
    """The bundled demo PDF goes through the same parser as an upload."""
    if not DEMO_PDF.exists():
        raise HTTPException(status_code=404, detail="The demo PDF is missing from data/demo.")
    text = text_from_upload(DEMO_PDF.name, DEMO_PDF.read_bytes())
    return store.create_upload(DEMO_PDF.name, text)


@app.get("/api/demo.pdf")
async def demo_pdf() -> FileResponse:
    if not DEMO_PDF.exists():
        raise HTTPException(status_code=404, detail="The demo PDF is missing from data/demo.")
    return FileResponse(DEMO_PDF, media_type="application/pdf", filename=DEMO_PDF.name)


@app.post("/api/matters/sample/{sample_id}", response_model=Matter)
async def open_sample(sample_id: str) -> Matter:
    try:
        return store.create_from_sample(sample_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Sample not found.") from exc


@app.get("/api/matters/{matter_id}", response_model=Matter)
async def get_matter(matter_id: str) -> Matter:
    return _matter_or_404(matter_id)


@app.post("/api/matters/{matter_id}/review")
async def review_matter(matter_id: str, mode: str = "fixture") -> StreamingResponse:
    if mode not in {"fixture", "live"}:
        raise HTTPException(status_code=400, detail="mode must be fixture or live.")
    matter = _matter_or_404(matter_id)
    if matter.status == "approved":
        raise HTTPException(status_code=409, detail="This matter is already closed.")
    if mode == "fixture" and not matter.sample_id:
        raise HTTPException(
            status_code=400,
            detail="Fixture mode only replays built-in samples. Uploads need live mode.",
        )
    if mode == "live":
        status = await llm.ping()
        if not status["reachable"]:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Local model server is not reachable at "
                    f"{status['base_url']}. Start mlx_lm.server on port 8080, "
                    "or run this review in fixture mode."
                ),
            )

    # The review is a background task. Closing the stream does not cancel it;
    # a second request for the same matter follows the run already in flight.
    run = trace_hub.running(matter_id)
    if run is None:

        async def work(run: Run) -> None:
            try:
                result = await run_review(matter_id, mode, run)
                run.emit("result", data=result.model_dump())
            except Exception as exc:
                logger.exception("review failed for %s", matter_id)
                run.emit("error", message=str(exc))

        run = trace_hub.start(matter_id, mode, work)
    return _sse(run)


@app.get("/api/matters/{matter_id}/events")
async def review_events(matter_id: str, after: int = -1) -> StreamingResponse:
    """Replay the latest review's trace, then follow it if it is still running."""
    _matter_or_404(matter_id)
    run = trace_hub.get(matter_id)
    if run is None:
        raise HTTPException(status_code=404, detail="This matter has no review trace yet.")
    return _sse(run, after)


def _sse(run: Run, after: int = -1) -> StreamingResponse:
    async def stream():
        async for event in trace_hub.follow(run, after):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/matters/{matter_id}/decision", response_model=Matter)
async def decide(matter_id: str, body: DecisionIn) -> Matter:
    _matter_or_404(matter_id)
    try:
        return store.apply_decision(matter_id, body)
    except DecisionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/api/matters/{matter_id}/audit")
async def audit(matter_id: str) -> list[dict]:
    matter = _matter_or_404(matter_id)
    return [event.model_dump() for event in matter.audit]


@app.get("/api/evals", response_model=EvalBundle)
async def get_evals() -> EvalBundle:
    return EvalBundle(fixture=evals.fixture_report(), live=evals.last_live_report())


@app.post("/api/evals/run", response_model=EvalReport)
async def run_eval(mode: str = "fixture") -> EvalReport:
    if mode == "fixture":
        return evals.fixture_report(force=True)
    if mode == "live":
        try:
            return await evals.live_report()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail="mode must be fixture or live.")
