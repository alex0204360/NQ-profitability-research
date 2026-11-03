import numpy as np
import pandas as pd

from tools.cloud_campaign01 import actions, targets


def test_targets_require_both_exits_to_mature_in_same_segment():
    times = pd.date_range("2026-10-01", periods=30, freq="min", tz="UTC")
    bars = pd.DataFrame({"timestamp": times, "segment": [1] * 15 + [2] * 15,
                         "open": np.arange(30.0), "close": np.arange(30.0) + 1})
    values, valid = targets(bars, pd.Timestamp("2026-10-01T00:29:00Z"))
    assert valid[0] and not valid[4]  # second delayed exit would cross a gap
    assert not valid[19]  # delayed exit matures at the cutoff
    assert values[0].tolist() == [20.0, 20.0]


def test_decision_requires_positive_stress_value_for_both_fills():
    estimates = np.array([[7, 8], [9, 5], [-7, -10], [-8, 4], [100, 100]])
    assert actions(estimates, np.array([True, True, True, True, False])).tolist() == [1, 0, -1, 0, 0]
