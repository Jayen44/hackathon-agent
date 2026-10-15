"""One vocabulary for "what happens to this claim".

Three layers used different words for it. The canonical one is OUTCOMES (the claims handler's queue, produced by
insurance/resolution.py). Finance's `decision` is an input to it, and the fleet's old labels map onto it:

    finance decision     -> outcome                 fleet legacy label    -> outcome
    pursue               -> PURSUE                  pursue                -> PURSUE
    dont_pursue          -> SETTLE_NO_RECOVERY      dont_pursue           -> SETTLE_NO_RECOVERY
    pull_logs_first      -> PULL_LOGS               pull_logs_first       -> PULL_LOGS
    not_av_recovery      -> RECOVER_FROM_INSURED    get_more_evidence     -> PULL_LOGS
    cannot_price         -> NEEDS_INPUTS            not_priced            -> NEEDS_INPUTS

Claims that never reach pricing (no collision, evidence failed integrity, human at fault) get CLOSE_NO_CLAIM, HUMAN_REVIEW and
MOTOR_CLAIM from resolve(); the fleet's `not_priced` cannot tell those apart, which is why callers should take the outcome
from `insurance.api.price_claim` rather than choose a label themselves.
"""
from __future__ import annotations

OUTCOMES = ("PURSUE", "PULL_LOGS", "NEEDS_INPUTS", "HUMAN_REVIEW", "SETTLE_NO_RECOVERY", "RECOVER_FROM_INSURED",
            "MOTOR_CLAIM", "CLOSE_NO_CLAIM")

FINANCE_TO_OUTCOME = {
    "pursue": "PURSUE",
    "dont_pursue": "SETTLE_NO_RECOVERY",
    "pull_logs_first": "PULL_LOGS",
    "not_av_recovery": "RECOVER_FROM_INSURED",
    "cannot_price": "NEEDS_INPUTS",
}

LEGACY_FLEET_TO_OUTCOME = {
    "pursue": "PURSUE",
    "dont_pursue": "SETTLE_NO_RECOVERY",
    "pull_logs_first": "PULL_LOGS",
    "get_more_evidence": "PULL_LOGS",
    "not_priced": "NEEDS_INPUTS",
}


def normalise(label: str) -> str:
    """Any known label (outcome, finance decision or legacy fleet label) -> canonical outcome. Unknown -> ValueError."""
    if label in OUTCOMES:
        return label
    if label in FINANCE_TO_OUTCOME:
        return FINANCE_TO_OUTCOME[label]
    if label in LEGACY_FLEET_TO_OUTCOME:
        return LEGACY_FLEET_TO_OUTCOME[label]
    raise ValueError(f"unknown claim label {label!r}; expected one of {OUTCOMES}")
