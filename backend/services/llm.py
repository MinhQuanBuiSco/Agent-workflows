from collections.abc import Awaitable, Callable

from openai import AsyncOpenAI

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

_client: AsyncOpenAI | None = None


class LLMUnreachable(RuntimeError):
    pass


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
    return _client


def reset_client() -> None:
    global _client
    _client = None


Delta = Callable[[str], Awaitable[None]]


async def complete(
    system: str,
    user: str,
    temperature: float,
    max_tokens: int = 2500,
    on_delta: Delta | None = None,
) -> str:
    """One chat completion. With on_delta, the reply streams token by token.

    Streaming changes nothing about what is returned. It only lets the trace
    show the model writing while the call is in flight.
    """
    client = get_client()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    if on_delta is None:
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=messages,
        )
        return response.choices[0].message.content or ""

    stream = await client.chat.completions.create(
        model=LLM_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=messages,
        stream=True,
    )
    parts: list[str] = []
    async for chunk in stream:
        if not chunk.choices:
            continue
        text = chunk.choices[0].delta.content
        if text:
            parts.append(text)
            await on_delta(text)
    return "".join(parts)


async def ping() -> dict:
    """Ask the OpenAI-compatible server which models it is serving.

    A connection error is a status, not an exception for the caller of /api/llm.
    Review refuses live mode separately when reachable is false.
    """
    try:
        models = await get_client().models.list()
        names = [item.id for item in models.data][:8]
        return {
            "reachable": True,
            "base_url": LLM_BASE_URL,
            "model": LLM_MODEL,
            "served_models": names,
        }
    except Exception as exc:
        return {
            "reachable": False,
            "base_url": LLM_BASE_URL,
            "model": LLM_MODEL,
            "served_models": [],
            "detail": str(exc),
        }


async def ensure_reachable() -> None:
    status = await ping()
    if not status["reachable"]:
        raise LLMUnreachable(
            "Local model server is not reachable at "
            f"{LLM_BASE_URL}. Start mlx_lm.server on port 8080, or run this review in fixture mode."
        )
