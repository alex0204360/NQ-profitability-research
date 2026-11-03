import numpy as np
import pandas as pd
import pytest

from tools.cloud_robust_teacher import robust_teacher


def bars():
    times = pd.date_range("2026-10-01T00:00Z", periods=30, freq="min")
    return pd.DataFrame({"timestamp": times, "segment": np.ones(30, dtype=int),
                         "open": np.full(30, 100.), "close": np.full(30, 100.)})


def test_teacher_keeps_losing_actions_and_two_fill_timings():
    frame = bars()
    frame.loc[1, "open"] = 98.
    frame.loc[2, "open"] = 99.
    frame.loc[10, "close"] = 105.
    frame.loc[11, "close"] = 106.
    net, valid, winner = robust_teacher(frame, pd.Timestamp("2026-10-01T00:30Z"))
    assert valid[0]
    np.testing.assert_allclose(net[0, 0], [8., 8.])
    np.testing.assert_allclose(net[0, 1], [-20., -20.])
    assert winner[0] == 1
    assert not valid[-1] and np.isnan(net[-1]).all() and winner[-1] == 0


def test_gap_or_unmatured_horizon_cannot_be_teacher_label():
    frame = bars()
    frame.loc[11:, "segment"] = 2
    _, valid, winner = robust_teacher(frame, pd.Timestamp("2026-10-01T00:30Z"))
    assert not valid[0] and winner[0] == 0
    frame = bars()
    _, valid, _ = robust_teacher(frame, pd.Timestamp("2026-10-01T00:11Z"))
    assert not valid[0]


def test_cost_must_be_finite_nonnegative():
    with pytest.raises(ValueError):
        robust_teacher(bars(), pd.Timestamp("2026-10-01T00:30Z"), float("nan"))
