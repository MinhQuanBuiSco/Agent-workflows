from services.citation import is_verbatim


def test_verbatim_span_passes():
    document = (
        "The confidentiality obligations survive for three (3) years "
        "from the date of each disclosure."
    )
    assert is_verbatim(document, document)


def test_collapsed_whitespace_still_passes():
    document = "The confidentiality obligations survive\nfor three (3) years."
    excerpt = "The confidentiality obligations survive for three (3) years."
    assert is_verbatim(excerpt, document)


def test_paraphrase_fails():
    document = "Obligations under this Agreement are mutual and apply equally to both parties."
    excerpt = "The parties agree to keep things confidential and follow industry norms."
    assert not is_verbatim(excerpt, document)


def test_empty_excerpt_fails():
    assert not is_verbatim("   ", "Mutual obligations apply.")
    assert not is_verbatim(None, "Mutual obligations apply.")
