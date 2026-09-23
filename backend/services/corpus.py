import json

from config import FIXTURES_DIR, GOLD_DIR, SAMPLES_DIR
from models import Extraction, GoldLabel


def list_gold() -> list[GoldLabel]:
    paths = sorted(GOLD_DIR.glob("*.json"))
    return [GoldLabel.model_validate(json.loads(path.read_text())) for path in paths]


def load_gold(sample_id: str) -> GoldLabel:
    path = GOLD_DIR / f"{sample_id}.json"
    if not path.exists():
        raise FileNotFoundError(sample_id)
    return GoldLabel.model_validate(json.loads(path.read_text()))


def load_sample_text(sample_id: str) -> str:
    path = SAMPLES_DIR / f"{sample_id}.txt"
    if not path.exists():
        raise FileNotFoundError(sample_id)
    return path.read_text()


def load_fixture(name: str) -> Extraction:
    path = FIXTURES_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(name)
    return Extraction.model_validate(json.loads(path.read_text()))
