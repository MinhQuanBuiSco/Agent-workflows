import io

import pdfplumber


def text_from_upload(filename: str, payload: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".txt"):
        return payload.decode("utf-8")
    if lower.endswith(".pdf"):
        with pdfplumber.open(io.BytesIO(payload)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n\n".join(pages).strip()
    raise ValueError("Upload a PDF or a TXT file.")
