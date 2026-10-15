"""Live checks against the REAL sim (skipped when the sim snapshot is unavailable). Slow: about 3 s per claim."""
import json
from pathlib import Path

import pytest

from insurance import sim_link
from insurance.bundle import load_bundle_file
from insurance.engine import decide
from insurance.sim_estimator import run_sim

pytestmark = pytest.mark.live_sim

EX = Path(__file__).resolve().parent.parent / "insurance" / "examples"
SNAP = Path(__file__).resolve().parent / "data" / "sim_snapshots.json"


@pytest.fixture(scope="module", autouse=True)
def need_sim():
    try:
        sim_link.load_estimate()
    except sim_link.SimUnavailable as e:
        pytest.skip(str(e))


@pytest.mark.parametrize("name", ["05_unavoidable_close_cutin", "06_borderline_needs_review", "21_pursue_cut_in"])
def test_snapshots_still_match_the_live_sim(name):
    snap = json.loads(SNAP.read_text())["cases"][name]
    live = run_sim(load_bundle_file(EX / f"{name}.json"), n=300)
    for k, d in snap["drivers"].items():
        assert live.estimators[k].result.p_avoid == pytest.approx(d["p_avoid"], abs=0.05)
    assert live.reproduced == snap["reproduced"]


def test_engine_verdicts_follow_the_live_sim():
    for name, liable in [("01_av_late_detection", "TECH_COMPANY"), ("05_unavoidable_close_cutin", "NO_FAULT_DRIVING"),
                         ("06_borderline_needs_review", "NEEDS_REVIEW")]:
        assert decide(load_bundle_file(EX / f"{name}.json")).liable == liable
