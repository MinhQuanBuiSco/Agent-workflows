import json
import re


def parse_json_object(text: str) -> dict:
    """Pull the first JSON object out of a local-model reply.

    Qwen sometimes wraps JSON in a fence. A reasoning model may also emit a
    think block. Neither is trusted as structure; only the object is.
    """
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("model reply did not contain a JSON object")
    parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("model reply JSON was not an object")
    return parsed
