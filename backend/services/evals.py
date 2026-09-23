from models import EvalReport
from services.corpus import list_gold, load_fixture, load_sample_text
from services.extractor import extract_contract
from services.llm import ensure_reachable
from services.playbook import load_playbook
from services.scoring import report_from_rows, score_against_gold

_fixture: EvalReport | None = None
_live: EvalReport | None = None


def fixture_report(*, force: bool = False) -> EvalReport:
    global _fixture
    if _fixture is not None and not force:
        return _fixture
    labels = list_gold()
    rows = []
    for gold in labels:
        rows.append(score_against_gold(gold, load_sample_text(gold.id), load_fixture(gold.id)))
    _fixture = report_from_rows("fixture", rows, labels)
    return _fixture


async def live_report() -> EvalReport:
    global _live
    await ensure_reachable()
    playbook = load_playbook()
    labels = list_gold()
    rows = []
    for gold in labels:
        text = load_sample_text(gold.id)
        extraction = await extract_contract(playbook, text)
        rows.append(score_against_gold(gold, text, extraction))
    _live = report_from_rows("live", rows, labels)
    return _live


def last_live_report() -> EvalReport | None:
    return _live


def clear_reports() -> None:
    global _fixture, _live
    _fixture = None
    _live = None
