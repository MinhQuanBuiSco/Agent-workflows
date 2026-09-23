def normalize_ws(text: str) -> str:
    return " ".join(text.split())


def is_verbatim(excerpt: str | None, document: str) -> bool:
    """True when the excerpt is a contiguous span of the contract.

    Whitespace is collapsed so a line wrap in a PDF does not fail a quote that
    is otherwise verbatim. Paraphrase still fails: the words have to be the
    contract's words.
    """
    if excerpt is None or not excerpt.strip():
        return False
    return normalize_ws(excerpt) in normalize_ws(document)
