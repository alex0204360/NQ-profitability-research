import numpy as np
import pandas as pd
import pytest

from tools.cloud_campaign05 import oracle_values, score_actions


def test_oracle_is_hindsight_label_with_both_fill_delays_and_cost():
    n = 35
    bars = pd.DataFrame({"timestamp": pd.date_range("2026-09-20T00:00Z", periods=n, freq="min"),
                         "segment": np.ones(n, int), "open": np.full(n, 100.),
                         "close": np.full(n, 100.)})
    bars.loc[1, "open"] = 98.
    bars.loc[2, "open"] = 99.
    bars.loc[3, "close"] = 103.
    bars.loc[4, "close"] = 104.
    output, valid = oracle_values(bars, pd.Timestamp("2026-09-20T00:35Z"))
    assert valid[0]
    np.testing.assert_allclose(output[0, :2], [4., -16.])
    assert output.shape == (n, 8)
    assert not valid[-1] and np.isnan(output[-1]).all()
    bars.loc[21:, "segment"] = 2
    _, valid = oracle_values(bars, pd.Timestamp("2026-09-20T00:35Z"))
    assert not valid[0]


def test_score_requires_aligned_eight_action_values():
    with pytest.raises(ValueError):
        score_actions(np.zeros((2, 8)), np.zeros((3, 8)))
