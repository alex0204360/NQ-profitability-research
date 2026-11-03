import numpy as np
import pandas as pd

from tools.cloud_campaign09 import decisions
from tools.temporal_path_state import completed_path


def test_path_prefix_and_gap_reset():
    n = 75
    times = pd.date_range('2026-10-01', periods=n, freq='min', tz='UTC')
    times = times.to_series(index=range(n))
    times.iloc[40:] += pd.Timedelta(minutes=5)
    bars = pd.DataFrame({'close': 25000 + np.arange(n) * .25,
                         'volume': np.arange(n) + 1, 'segment': [1] * 40 + [2] * 35,
                         'timestamp': times.to_numpy()})
    atr = np.full(n, 3.)
    full, ready = completed_path(bars, atr)
    prefix, prefix_ready = completed_path(bars.iloc[:36], atr[:36])
    np.testing.assert_array_equal(full[:36], prefix)
    np.testing.assert_array_equal(ready[:36], prefix_ready)
    assert ready[39] and not ready[40] and not ready[71] and ready[72]


def test_decisions_abstain_without_positive_predicted_value():
    prediction = np.array([[2., -1.], [-2., 3.], [-1., -2.], [5., 4.]])
    actual = decisions(prediction, np.array([1, 1, 1, 0], bool), np.ones(4, bool))
    np.testing.assert_array_equal(actual, [1, -1, 0, 0])
