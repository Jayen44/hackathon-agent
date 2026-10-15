from agent import model


def test_first_assessment_is_material():
    assert model.changed_materially(None, {"score": 0, "decision": "hold"})


def test_small_move_is_not_material():
    a = {"score": 1.00, "decision": "hold"}
    b = {"score": 1.01, "decision": "hold"}
    assert not model.changed_materially(a, b)


def test_flip_is_material():
    a = {"score": 1.0, "decision": "hold"}
    b = {"score": 1.0, "decision": "act"}
    assert model.changed_materially(a, b)
