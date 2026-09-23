from collections.abc import Awaitable, Callable

from models import Extraction, Playbook
from services.json_text import parse_json_object
from services.llm import Delta, complete
from services.playbook import render_extraction_prompt

SYSTEM = (
    "You extract facts from contracts. You do not decide whether a clause is acceptable. "
    "Copy excerpts verbatim. Reply with JSON only."
)


Retry = Callable[[str], Awaitable[None]]


async def extract_contract(
    playbook: Playbook,
    contract_text: str,
    on_delta: Delta | None = None,
    on_retry: Retry | None = None,
) -> Extraction:
    prompt = render_extraction_prompt(playbook, contract_text)
    last_error = "no attempt"
    user = prompt
    for _ in range(2):
        raw = await complete(SYSTEM, user, temperature=0, on_delta=on_delta)
        try:
            return Extraction.model_validate(parse_json_object(raw))
        except Exception as exc:
            last_error = str(exc)
            if on_retry is not None:
                await on_retry(last_error)
            user = (
                prompt
                + "\n\nYour previous reply was invalid JSON for the schema: "
                + last_error
                + "\nReply with one JSON object only."
            )
    raise ValueError(f"Model did not return a valid extraction: {last_error}")
