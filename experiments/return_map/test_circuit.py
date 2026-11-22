"""Geometry, execution-time input boundaries, state isolation, and frozen controls."""
import numpy as np
import pandas as pd

from circuit import encode, trace, weights


def example(offsets, *, reset=None, direction=1):
    index = pd.date_range("2026-09-14 10:00", periods=len(offsets), freq="min")
    features = pd.DataFrame({"age": np.arange(32, 32 + len(index)), "effort": 0.,
                             "motion": 0., "scale": 10.}, index=index)
    features.iloc[0, 1] = 0.5
    if reset is not None:
        features.loc[index[reset]:, "age"] = np.arange(1, len(index) - reset + 1)
    return trace(15000. + direction * np.array(offsets), features, weights())


def test_addressed_turn_and_reflection():
    for side in (1, -1):
        s = example([0., 11., 14., 4., 2., 3., 8., 10.], direction=side)
        np.testing.assert_allclose(s.return_map * side, [0, 0, 0, 3, 4, 3.5, 1, 0])
        np.testing.assert_allclose(s.confirmed * side, [0, 0, 0, 0, 0, 3.5, 1, 0])
        np.testing.assert_allclose(s.confirmed_equal * 2, s.confirmed)


def test_first_contact_traversal_expiry_and_reset():
    for path in ([0, 12, -1, 4, 5], [0, 12, 4, 2, -1, 4], [0, 12, 4, 12, 5]):
        s = example(path)
        assert not s.confirmed.any()
        assert s.live_sites.iloc[-1] == 0
    s = example([0, 12] + [8] * 30 + [4, 5])
    assert not s.return_map.any()
    s = example([0, 12, 4, 5, 6], reset=3)
    assert s.live_sites.iloc[3:].sum() == 0
    assert s.return_map.iloc[3:].isna().all()


def test_full_encoder_prefix_and_gap():
    rng = np.random.default_rng(316)
    index = pd.date_range("2026-09-14 10:00", periods=180, freq="min", tz="America/New_York")
    close = 15000. + rng.integers(-8, 9, len(index)).cumsum() / 4
    bars = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": rng.integers(10, 300, len(index))}, index=index)
    full = encode(bars)
    pd.testing.assert_frame_equal(full.iloc[:99], encode(bars.iloc[:99]))
    segmented = encode(bars.drop(index[90]))
    pd.testing.assert_frame_equal(segmented.loc[index[91]:], encode(bars.iloc[91:]), check_freq=False)
