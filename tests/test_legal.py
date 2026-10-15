"""Legal regime, limitation clocks and P(liable to victim) scaling (docs/legal-basis.md)."""
import copy
import json
from datetime import date
from pathlib import Path

import pytest

from insurance.bridge import assess_bundle, to_avoidance_result
from insurance.bundle import BundleError, load_bundle_file
from insurance.legal import Legal, limitation_deadline
from insurance.resolution import resolve

EX = Path(__file__).resolve().parent.parent / "insurance" / "examples"
TODAY = date(2026, 10, 15)


def test_s5_deadline_is_two_years_from_settlement():
    d = limitation_deadline(Legal(recovery_route="AEVA_s5", settlement_date="2026-12-01"), TODAY)
    assert d.due == date(2028, 12, 1) and d.days_left == (date(2028, 12, 1) - TODAY).days and not d.urgent


def test_cpa_longstop_beats_three_years():
    d = limitation_deadline(Legal(recovery_route="CPA_1987", knowledge_date="2026-10-01", supply_date="2017-01-01"), TODAY)
    assert d.due == date(2027, 1, 1) and "longstop" in d.basis


def test_no_deadline_without_dates_and_leap_day():
    assert limitation_deadline(Legal(recovery_route="AEVA_s5"), TODAY) is None
    d = limitation_deadline(Legal(recovery_route="AEVA_s5", settlement_date="2028-02-29"), TODAY)
    assert d.due == date(2030, 2, 28)


def test_p_liable_scales_share_and_widens_interval():
    from tests.support import stub_result
    cf = stub_result(0.9, n=200)
    plain = to_avoidance_result("m", cf)
    scaled = to_avoidance_result("m", cf, (0.5, 0.6, 0.9))
    assert scaled.p_avoid == pytest.approx(plain.p_avoid * 0.6)
    assert scaled.ci90[0] < scaled.p_avoid < scaled.ci90[1] or scaled.ci90[0] <= scaled.p_avoid <= scaled.ci90[1]


def test_bundle_rejects_bad_legal_fields(tmp_path):
    d = json.loads((EX / "01_av_late_detection.json").read_text())
    for bad in ({"regime": "nope"}, {"recovery_route": "x"}, {"settlement_date": "01/03/2027"},
                {"p_liable_to_victim": [0.9, 0.5, 0.7]}):
        e = copy.deepcopy(d)
        e["legal"] = bad
        p = tmp_path / "b.json"
        p.write_text(json.dumps(e))
        with pytest.raises(BundleError):
            load_bundle_file(p)


def test_pursue_example_carries_deadline_and_legal_steps():
    b = load_bundle_file(EX / "21_pursue_cut_in.json")
    from tests.support import two
    r = assess_bundle(b, estimators=two(0.95, 1.0), reproduced=True, today=date(2027, 2, 1))
    assert r.deadline.due == date(2029, 3, 1) and any("Limitation" in n for n in r.notes)
    x = resolve(r, b)
    assert x.outcome == "PURSUE" and "Limitation" in x.next_steps[0].action
    urgent = assess_bundle(b, estimators=two(0.95, 1.0), reproduced=True, today=date(2029, 1, 15))
    assert "URGENT" in resolve(urgent, b).next_steps[0].action
