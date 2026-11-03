import numpy as np
import pandas as pd

from tools.cloud_campaign02 import choose, values


def test_teacher_targets_stop_at_gap_and_maturity_boundary():
    times = pd.date_range("2026-10-01", periods=55, freq="min", tz="UTC")
    bars = pd.DataFrame({"timestamp": times, "segment": [1] * 25 + [2] * 30,
                         "open": np.arange(55.0), "close": np.arange(55.0) + 1})
    outcome, valid = values(bars, pd.Timestamp("2026-10-01T00:52:00Z"))
    assert valid[0] and not valid[4]
    assert not valid[31]
    assert outcome[0, 0] == 6  # three bars from next open, one MNQ contract


def test_student_selects_best_robust_horizon_and_abstains_when_unready():
    predictions = np.array([[7, 8, 10, 9, 12, 5, -11, -10],
                            [1, 2, -1, -2, 0, 1, 2, 0]])
    signal, horizon, value = choose(predictions, np.array([True, False]))
    assert signal.tolist() == [-1, 0]
    assert horizon[0] == 20
    assert value[0] == 4
