import numpy as np
import pandas as pd

from brain import activations, weights


def sample():
    rng = np.random.default_rng(14)
    stamps = pd.date_range("2026-09-15 09:30", periods=100, freq="min", tz="America/New_York")
    close = 100 + rng.integers(-4, 5, len(stamps)).cumsum() / 4
    return pd.DataFrame(dict(close=close, high=close+1, low=close-1,
                             volume=rng.integers(1, 100, len(stamps))), index=stamps)


def test_prefix_reset_reflection():
    bars = sample()
    a = activations(bars)
    pd.testing.assert_frame_equal(a.iloc[:51], activations(bars.iloc[:51]))
    after_gap = activations(bars.drop(bars.index[49]))
    pd.testing.assert_frame_equal(after_gap.iloc[49:], activations(bars.iloc[50:]), check_freq=False)
    mirror = bars.assign(close=200-bars.close, high=200-bars.low, low=200-bars.high)
    np.testing.assert_allclose(a.area, -activations(mirror).area, atol=1e-12, equal_nan=True)


def test_area_equals_explicit_ordered_pairs():
    a = activations(sample())
    n = len(a)
    e, q = a.effort.to_numpy(), a.motion.to_numpy()
    # Sum over i < j. An older i decays both before and after the pair is formed.
    analytic = sum(0.125 * 0.875**(n-2-i) * (e[i]*q[j] - q[i]*e[j])
                   for i in range(n) for j in range(i+1, n))
    np.testing.assert_allclose(a.area.iloc[-1], a.scale.iloc[-1]*analytic, atol=1e-12)
    cfg = weights()
    left, right = np.array(cfg["left"]), np.array(cfg["right"])
    def read(x):
        return np.array(cfg["readout"]) @ ((left @ x) * (right @ x))
    assert read([0.125, 0, 0, 1]) == -read([0, 0.125, 1, 0]) == 0.125


def test_stock_conservation_and_no_same_bar_release():
    from brain import transport
    cfg = weights("reservoir")
    fake = pd.DataFrame({"age":[1, 2, 3, 4], "effort":[1, 0, 0, 0], "motion":[0, .25, -1, 1]})
    charge, stock, signed, forecast = transport(fake, cfg, np.array(cfg["charge"])).T
    np.testing.assert_allclose(charge, [1, 0, 0, 0])
    np.testing.assert_allclose(signed, [0, .25, -.75*.875, 0])
    np.testing.assert_allclose(stock, [1, .75*.875, 0, 0])
    assert np.abs(signed).sum() <= 1
    assert forecast[0] == 0


def test_stock_prefix_mirror_and_reset():
    b = sample()
    for m in ["reservoir", "volume_control"]:
        a = activations(b, m)
        pd.testing.assert_frame_equal(a.iloc[:57], activations(b.iloc[:57], m))
        after_gap = activations(b.drop(b.index[49]), m)
        pd.testing.assert_frame_equal(after_gap.iloc[49:], activations(b.iloc[50:], m), check_freq=False)
        mirrored = b.assign(close=200-b.close, high=200-b.low, low=200-b.high)
        np.testing.assert_allclose(a[m], -activations(mirrored, m)[m], atol=1e-12, equal_nan=True)
