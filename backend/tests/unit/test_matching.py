from app.core.matching import Candidate, brand_ambiguous, confidence, normalise, selling_qty


def test_normalise_expands_trade_shorthand_and_imperial():
    assert normalise('3/4" cu elbow comp') == "22mm copper elbow compression"
    assert normalise('1 1/4" iso valve') == "35mm isolating valve"


def test_selling_qty_converts_pieces_to_packs():
    assert selling_qty(20, "pcs", 10) == 2
    assert selling_qty(20, None, 10) == 20
    assert selling_qty(5, "pcs", 1) == 5


def test_near_tie_gets_low_confidence():
    tie = [Candidate(1, "A", "a", 0.80), Candidate(2, "B", "b", 0.79)]
    clear = [Candidate(1, "A", "a", 0.80), Candidate(2, "B", "b", 0.60)]
    assert confidence(tie) < 0.3 < confidence(clear)


def test_confidence_never_negative():
    out_of_order = [Candidate(1, "A", "a", 0.5), Candidate(2, "B", "b", 0.7)]
    assert confidence(out_of_order) == 0.0


def test_brand_ambiguity():
    c = [Candidate(1, "CU-EL90-NORT-15-COMP", "", .8), Candidate(2, "CU-EL90-PROF-15-COMP", "", .8)]
    assert brand_ambiguous("cu elbow 15mm comp", c)
    assert not brand_ambiguous("northway cu elbow 15mm comp", c)
