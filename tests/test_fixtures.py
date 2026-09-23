from models import Extraction
from services.corpus import list_gold, load_fixture, load_sample_text
from services.scoring import score_extraction


def test_recorded_extractions_match_gold_routes_and_verdicts():
    seen = set()
    for gold in list_gold():
        seen.add(gold.route)
        text = load_sample_text(gold.id)
        extraction = load_fixture(gold.id)
        route, _reasons, positions = score_extraction(text, extraction)
        assert route == gold.route, gold.id
        by_id = {position.id: position for position in positions}
        assert set(by_id) == set(gold.positions)
        for position_id, expected in gold.positions.items():
            assert by_id[position_id].verdict == expected, f"{gold.id}:{position_id}"
            if by_id[position_id].present:
                assert by_id[position_id].citation_ok is True
    assert seen == {"green", "yellow", "red", "out_of_playbook"}


def test_paraphrased_quotes_cannot_clear_a_clean_nda():
    text = load_sample_text("nda-clean-mutual")
    extraction = load_fixture("bad-paraphrase")
    route, _reasons, positions = score_extraction(text, extraction)
    assert route == "red"
    mutuality = next(position for position in positions if position.id == "mutuality")
    assert mutuality.verdict == "ungrounded"
    assert mutuality.citation_ok is False
    assert mutuality.model_verdict == "ungrounded"


def test_missing_position_uses_if_absent_and_cannot_go_green():
    text = load_sample_text("nda-clean-mutual")
    extraction = Extraction(document_type="nda", counterparty="Northwind Labs LLC", positions=[])
    route, _reasons, positions = score_extraction(text, extraction)
    by_id = {position.id: position.verdict for position in positions}
    assert by_id["mutuality"] == "reject"
    assert by_id["residuals"] == "accept"
    assert by_id["ai_training"] == "accept"
    assert by_id["compelled_notice"] == "fallback"
    assert by_id["personal_data"] == "reject"
    assert route == "red"
