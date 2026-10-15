"""Runs only when the `sim` package is importable (after merging the sim branch)."""
import json
from pathlib import Path

import pytest

pytest.importorskip("sim")

from insurance.bundle import load_bundle  # noqa: E402
from insurance.counterfactual import KinematicEstimator  # noqa: E402
from insurance.engine import decide  # noqa: E402
from insurance.sim_adapter import SimEstimator  # noqa: E402

EX = Path(__file__).resolve().parent.parent / "insurance" / "examples"


def bundle(name):
    return load_bundle(json.loads((EX / f"{name}.json").read_text(encoding="utf-8")))


@pytest.mark.parametrize("name", ["01_av_late_detection", "05_unavoidable_close_cutin",
                                  "06_borderline_needs_review", "15_lead_braking_avoidable",
                                  "16_lead_braking_unavoidable", "17_cut_in_avoidable", "18_cut_in_unavoidable"])
def test_sim_agrees_with_closed_form(name):
    c = bundle(name).conflict
    a, b = SimEstimator(n=300).estimate(c), KinematicEstimator(n=300).estimate(c)
    assert abs(a.p_avoid - b.p_avoid) < 0.15
    assert (a.avoids_at_p5, a.avoids_at_p95) == (b.avoids_at_p5, b.avoids_at_p95)


def test_engine_verdicts_unchanged_with_sim_estimator():
    for name, liable in [("01_av_late_detection", "TECH_COMPANY"),
                         ("05_unavoidable_close_cutin", "NO_FAULT_DRIVING"),
                         ("06_borderline_needs_review", "NEEDS_REVIEW")]:
        assert decide(bundle(name), estimator=SimEstimator(n=300)).liable == liable
