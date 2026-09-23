from functools import lru_cache

import yaml

from config import PLAYBOOK_PATH
from models import Playbook


@lru_cache(maxsize=1)
def load_playbook() -> Playbook:
    raw = yaml.safe_load(PLAYBOOK_PATH.read_text())
    return Playbook.model_validate(raw)


def render_extraction_prompt(playbook: Playbook, contract_text: str) -> str:
    blocks: list[str] = []
    for position in playbook.positions:
        field_lines = "\n".join(
            f"    - {field.name} ({field.type}): {field.description.strip()}"
            for field in position.fields
        )
        blocks.append(
            f"- id: {position.id}\n"
            f"  what to look for: {position.requirement.strip()}\n"
            f"  fields:\n{field_lines}"
        )
    joined = "\n".join(blocks)
    return f"""Read the contract and return JSON only. No markdown.

Schema:
{{
  "document_type": "nda" or "other",
  "counterparty": "the party that is not Acme Industries, or null",
  "positions": [
    {{"id": "<id>", "present": true or false, "excerpt": "verbatim span or null", "fields": {{}}}}
  ]
}}

Rules:
- Include exactly one object for every position id below.
- document_type is "nda" only for a non-disclosure or confidentiality agreement.
  An order form, statement of work, or subscription order is "other".
- When present is false, excerpt must be null and fields must be {{}}.
- When present is true, excerpt must be copied verbatim from the contract.
  Same words, contiguous span. Do not paraphrase.
- Do not add a verdict, a risk level, or a route. You do not decide acceptability.

Positions:
{joined}

CONTRACT:
{contract_text}
"""


def render_comment_prompt(items: list[dict]) -> str:
    lines = []
    for item in items:
        lines.append(
            f"- id: {item['id']}\n"
            f"  verdict: {item['verdict']}\n"
            f"  why: {item['rationale']}\n"
            f"  playbook language you must keep: {item['fallback_comment']}\n"
            f"  quote: {item['excerpt'] or '(not in the contract)'}"
        )
    body = "\n".join(lines)
    return f"""Write one redline comment per item. JSON only.

Schema:
{{"comments": [{{"id": "<id>", "comment": "<one or two sentences>"}}]}}

Use the playbook language. Do not soften a reject into a suggestion that the clause is fine.
Do not invent a new negotiating position.

Items:
{body}
"""
