import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO_ROOT / "data"))
PLAYBOOK_PATH = DATA_DIR / "playbook" / "acme-nda.yaml"
SAMPLES_DIR = DATA_DIR / "samples"
GOLD_DIR = DATA_DIR / "gold"
FIXTURES_DIR = DATA_DIR / "fixtures"
UPLOADS_DIR = DATA_DIR / "uploads"
# A real PDF for demos where nobody has a contract at hand. Live mode only: it has no fixture.
DEMO_PDF = DATA_DIR / "demo" / "Bluefin-Analytics-NDA.pdf"

# The model server runs on the macOS host. MLX needs Metal, which the
# Linux Docker VM does not have. Override LLM_BASE_URL in Compose.
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8080/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "mlx-community/Qwen2.5-14B-Instruct-8bit")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "not-needed")

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", '["http://localhost:5173"]')
MAX_FILE_SIZE_MB = 10
APP_VERSION = "0.1.0"


def cors_origins() -> list[str]:
    parsed = json.loads(CORS_ORIGINS)
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise RuntimeError("CORS_ORIGINS must be a JSON list of strings")
    return parsed
