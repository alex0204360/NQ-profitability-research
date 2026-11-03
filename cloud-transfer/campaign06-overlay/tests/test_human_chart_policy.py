import numpy as np
import pandas as pd

from tools.human_chart_policy import calibrate, chart_setups, confirmed_trendlines, signals


def test_trendline_waits_for_two_confirmed_pivots_and_ignores_future_suffix():
    frame = pd.DataFrame({"segment": np.ones(20, int), "low": np.full(20, 10.),
                          "high": np.full(20, 12.)})
    frame.loc[3, "low"] = 5.
    frame.loc[10, "low"] = 6.
    first = confirmed_trendlines(frame)[0]
    assert np.isnan(first[11])
    assert np.isclose(first[12], 6 + 2 / 7)
    frame.loc[15, "low"] = 1.
    second = confirmed_trendlines(frame)[0]
    np.testing.assert_allclose(first[:13], second[:13], equal_nan=True)


def test_horizontal_support_retest_is_causal_and_explainable():
    bars = pd.DataFrame({"segment": [1], "open": [100.], "high": [100.75],
                         "low": [100.], "close": [100.5]})
    states = pd.DataFrame({"atr14": [2.], "ema_spread_atr": [.2], "trend_strength": [.3],
                           "support_distance_atr": [.25], "resistance_distance_atr": [1.],
                           "support_confirmed": [1], "resistance_confirmed": [1],
                           "support_missing": [0], "resistance_missing": [0]})
    setups, levels = chart_setups(bars, states, np.array([True]))
    assert setups[0, 0, 0] and not setups[0, 0, 1]
    assert levels["horizontal_support"][0] == 100.


def test_probability_gate_needs_both_payoff_and_support():
    setups = np.zeros((30, 2, 2), bool)
    setups[:, 0, 0] = True
    robust = np.zeros((30, 2), float)
    robust[:20, 0] = 10.
    robust[20:, 0] = -2.
    calibration = calibrate(setups, robust, np.ones(30, bool), np.ones(30, bool))
    assert calibration["horizontal_long"]["allowed"]
    action, reasons = signals(setups, calibration, gated=True)
    assert (action == 1).all() and reasons[0] == "horizontal_long_retest"
    calibration["horizontal_long"]["allowed"] = False
    action, reasons = signals(setups, calibration, gated=True)
    assert (action == 0).all() and reasons[0] == "setup_failed_probability_gate"
