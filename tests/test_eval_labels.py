"""Loader test for eval/labels.csv (issue #5)."""
import pytest

from eval.labels import ALLOWED, load_labels


def test_twenty_valid_labels():
    rows = load_labels()
    assert len(rows) == 20
    assert {r.who_pays for r in rows} == ALLOWED["who_pays"]              # every outcome represented
    assert {r.avoidable_by_careful_driver for r in rows} == ALLOWED["avoidable_by_careful_driver"]
    assert all(r.source.startswith("synthetic:") for r in rows)


def test_bad_label_is_rejected(tmp_path):
    p = tmp_path / "bad.csv"
    text = open("eval/labels.csv").read().replace(",yes,yes,tech,", ",yes,maybe,tech,", 1)
    p.write_text(text)
    with pytest.raises(ValueError):
        load_labels(p)
