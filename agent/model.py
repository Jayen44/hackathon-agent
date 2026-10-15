"""Deterministic domain logic. Finance team owns this file.

Keep it pure: inputs in, numbers out. No I/O, no LLM calls.
"""


def evaluate(state: dict, inputs: dict) -> dict:
    """Return the agent's current assessment.

    TODO(finance): replace with real logic. Return plain dicts so the
    loop, store and dashboard stay decoupled from the model.
    """
    return {"score": 0.0, "decision": "hold", "drivers": {}}


def changed_materially(prev: dict | None, new: dict, threshold: float = 0.05) -> bool:
    """True when the decision flipped or the score moved more than threshold."""
    if prev is None:
        return True
    if prev["decision"] != new["decision"]:
        return True
    return abs(prev["score"] - new["score"]) > threshold
