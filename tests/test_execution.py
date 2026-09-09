"""Execution-model regressions use synthetic prices, never market/holdout data."""

from dataclasses import FrozenInstanceError

import numpy as np
import pandas as pd
import pytest

from nqprofit.execution import Action, action_grid, payoff_matrix, quantize_distance, simulate_trade


def bars(count=50):
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-02T10:00:00Z", periods=count, freq="min"),
            "open": np.full(count, 100.0),
            "high": np.full(count, 100.5),
            "low": np.full(count, 99.5),
            "close": np.full(count, 100.0),
            "volume": np.full(count, 10),
        }
    )
    return frame


def set_bar(frame, row, open_, high, low, close):
    frame.loc[row, ["open", "high", "low", "close"]] = [open_, high, low, close]


def test_grid_is_complete_unique_frozen_and_in_canonical_tie_order():
    actions = action_grid()
    assert isinstance(actions, tuple)
    assert len(actions) == 1080
    assert len({a.action_id for a in actions}) == 1080
    expected = [
        (h, sl, tp, direction)
        for h in range(1, 46)
        for sl in (0.5, 1.0, 2.0)
        for tp in (0.5, 1.0, 2.0, 3.0)
        for direction in (1, -1)
    ]
    assert [(a.horizon, a.sl_atr, a.tp_atr, a.direction) for a in actions] == expected
    assert Action(1, 1, 1, 5).action_id == Action(1, 1.0, 1.0, 5).action_id
    with pytest.raises(FrozenInstanceError):
        actions[0].horizon = 46


@pytest.mark.parametrize("horizon", [0, -1, 46, 60, 2.5, True])
def test_action_rejects_invalid_or_out_of_scope_windows(horizon):
    with pytest.raises(ValueError, match="rejected.*out of scope"):
        Action(1, 1, 1, horizon)


@pytest.mark.parametrize("direction", [0, 2, -2, True, "long"])
def test_action_rejects_invalid_direction(direction):
    with pytest.raises(ValueError):
        Action(direction, 1, 1, 5)


@pytest.mark.parametrize("tp, sl", [(0, 1), (-1, 1), (1, 0), (np.nan, 1), (1, np.inf)])
def test_action_rejects_invalid_distances(tp, sl):
    with pytest.raises(ValueError):
        Action(1, tp, sl, 5)


@pytest.mark.parametrize(
    "atr,multiple,expected",
    [
        (0.1, 0.5, 0.25),
        (0.125, 1, 0.25),
        (0.374999, 1, 0.25),
        (0.375, 1, 0.5),
        (0.625, 1, 0.75),
        (1.25, 0.5, 0.75),
        (4, 3, 12),
    ],
)
def test_distance_rounding_is_half_up_with_one_tick_minimum(atr, multiple, expected):
    assert quantize_distance(atr, multiple) == expected


@pytest.mark.parametrize("atr,multiple", [(0, 1), (-1, 1), (np.nan, 1), (1, 0), (1, np.inf)])
def test_distance_rounding_rejects_invalid_inputs(atr, multiple):
    with pytest.raises(ValueError):
        quantize_distance(atr, multiple)


@pytest.mark.parametrize(
    "direction,high,low,reason,gross,exit_price",
    [
        (1, 105, 99, "tp", 4, 104),
        (-1, 101, 95, "tp", 4, 96),
        (1, 101, 95, "sl", -4, 96),
        (-1, 105, 99, "sl", -4, 104),
    ],
)
def test_next_open_entry_and_single_barrier_fills(direction, high, low, reason, gross, exit_price):
    frame = bars()
    frame.loc[0, "close"] = 99.75
    set_bar(frame, 1, 100, high, low, 100)
    result = simulate_trade(frame, 0, Action(direction, 1, 1, 3), atr=4, cost=1.5)
    assert result["entry_price"] == 100
    assert result["exit_price"] == exit_price
    assert result["exit_reason"] == reason
    assert result["gross_points"] == gross
    assert result["net_points"] == gross - 1.5
    assert result["resolution_bars"] == 1
    assert result["ambiguous"] is False
    assert pd.Timestamp(result["entry_time"]) == frame.loc[1, "timestamp"]
    assert pd.Timestamp(result["exit_time"]) == frame.loc[1, "timestamp"] + pd.Timedelta(minutes=1)
    assert result["detection_index"] == 0
    assert result["direction"] == direction
    assert result["tp_points"] == result["sl_points"] == 4
    assert result["horizon"] == 3
    assert result["action_id"] == Action(direction, 1, 1, 3).action_id


@pytest.mark.parametrize(
    "direction,open_,expected_price,reason,gross",
    [
        (1, 106, 104, "tp", 4),
        (1, 94, 94, "sl", -6),
        (-1, 94, 96, "tp", 4),
        (-1, 106, 106, "sl", -6),
    ],
)
def test_opening_gaps_use_worse_stop_price_and_cap_target(
    direction, open_, expected_price, reason, gross
):
    frame = bars()
    set_bar(frame, 2, open_, open_ + 0.5, open_ - 0.5, open_)
    result = simulate_trade(frame, 0, Action(direction, 1, 1, 3), atr=4)
    assert result["exit_reason"] == reason
    assert result["exit_price"] == expected_price
    assert result["gross_points"] == gross
    assert result["resolution_bars"] == 2
    assert result["ambiguous"] is False


@pytest.mark.parametrize("direction", [1, -1])
def test_intrabar_both_touches_is_adverse_and_flagged(direction):
    frame = bars()
    set_bar(frame, 1, 100, 105, 95, 100)
    result = simulate_trade(frame, 0, Action(direction, 1, 1, 5), atr=4)
    assert result["exit_reason"] == "sl"
    assert result["ambiguous"] is True
    assert result["gross_points"] == -4
    assert result["net_points"] == -5


@pytest.mark.parametrize("open_,reason,price", [(105, "tp", 104), (95, "sl", 95)])
def test_open_is_resolved_before_intrabar_ambiguity(open_, reason, price):
    frame = bars()
    set_bar(frame, 2, open_, 110, 90, 100)
    result = simulate_trade(frame, 0, Action(1, 1, 1, 3), atr=4)
    assert result["exit_reason"] == reason
    assert result["exit_price"] == price
    assert result["ambiguous"] is False


@pytest.mark.parametrize("direction", [1, -1])
@pytest.mark.parametrize("horizon", [1, 45])
def test_timeout_is_actual_signed_close_payoff_at_exact_horizon(direction, horizon):
    frame = bars()
    set_bar(frame, horizon, 100, 102, 99.5, 101.75)
    set_bar(frame, horizon + 1, 100, 110, 90, 100)
    result = simulate_trade(frame, 0, Action(direction, 1, 1, horizon), atr=4)
    assert result["exit_reason"] == "timeout"
    assert result["resolution_bars"] == horizon
    assert result["gross_points"] == direction * 1.75
    assert result["net_points"] == direction * 1.75 - 1
    assert pd.Timestamp(result["exit_time"]) == frame.loc[horizon, "timestamp"] + pd.Timedelta(
        minutes=1
    )


def test_hit_on_45th_bar_is_included():
    frame = bars()
    set_bar(frame, 45, 100, 104, 100, 104)
    result = simulate_trade(frame, 0, Action(1, 1, 1, 45), atr=4)
    assert result["exit_reason"] == "tp"
    assert result["resolution_bars"] == 45


@pytest.mark.parametrize("problem", ["missing", "segment", "contract"])
def test_unobserved_open_trade_is_censored_without_extending_holding_cap(problem):
    frame = bars()
    frame["segment_id"] = 0
    frame["contract"] = "NQH4"
    if problem == "missing":
        frame = frame.drop(index=2)
    elif problem == "segment":
        frame.loc[2:, "segment_id"] = 1
    else:
        frame.loc[2:, "contract"] = "NQM4"
    result = simulate_trade(frame, 0, Action(1, 1, 1, 3), atr=4)
    assert result["exit_reason"] == "censored"
    assert result["entry_price"] == 100
    assert result["exit_price"] is None
    assert result["resolution_bars"] is None
    assert result["gross_points"] is None
    assert result["net_points"] is None
    assert pd.Timestamp(result["exit_time"]) == pd.Timestamp("2024-01-02T10:04:00Z")


@pytest.mark.parametrize("problem", ["missing", "segment", "contract", "end"])
def test_missing_required_entry_is_an_attempt_with_intended_times(problem):
    frame = bars()
    if problem == "missing":
        frame = frame.drop(index=1)
    elif problem == "segment":
        frame["segment_id"] = [0] + [1] * 49
    elif problem == "contract":
        frame["contract"] = ["NQH4"] + ["NQM4"] * 49
    else:
        frame = frame.iloc[:1]
    result = simulate_trade(frame, 0, Action(1, 1, 1, 3), atr=4)
    assert result["exit_reason"] == "censored"
    assert result["entry_price"] is None
    assert pd.Timestamp(result["entry_time"]) == pd.Timestamp("2024-01-02T10:01:00Z")
    assert pd.Timestamp(result["exit_time"]) == pd.Timestamp("2024-01-02T10:04:00Z")


@pytest.mark.parametrize("problem", ["missing", "segment", "contract", "end"])
def test_observed_early_exit_survives_later_missing_unused_observations(problem):
    frame = bars()
    set_bar(frame, 1, 100, 104, 99.5, 104)
    if problem == "missing":
        frame = frame.drop(index=2)
    elif problem == "segment":
        frame["segment_id"] = [0, 0] + [1] * 48
    elif problem == "contract":
        frame["contract"] = ["NQH4", "NQH4"] + ["NQM4"] * 48
    else:
        frame = frame.iloc[:2]
    result = simulate_trade(frame, 0, Action(1, 1, 1, 45), atr=4)
    assert result["exit_reason"] == "tp"
    assert result["resolution_bars"] == 1
    assert result["net_points"] == 3


def test_chosen_short_horizon_does_not_require_45_future_bars():
    frame = bars(2)
    result = simulate_trade(frame, 0, Action(1, 1, 1, 1), atr=4)
    assert result["exit_reason"] == "timeout"
    assert result["net_points"] == -1


def test_detection_index_is_positional_not_dataframe_label():
    frame = bars()
    frame.index = np.arange(100, 150)
    result = simulate_trade(frame, 0, Action(1, 1, 1, 1), atr=4)
    assert result["exit_reason"] == "timeout"


@pytest.mark.parametrize("index", [-1, 50, 1.5, True])
def test_invalid_detection_index_rejected(index):
    with pytest.raises((ValueError, IndexError, TypeError)):
        simulate_trade(bars(), index, Action(1, 1, 1, 1), atr=4)


@pytest.mark.parametrize("cost", [-1, np.nan, np.inf])
def test_invalid_cost_rejected(cost):
    with pytest.raises(ValueError):
        simulate_trade(bars(), 0, Action(1, 1, 1, 1), atr=4, cost=cost)


def test_naive_timestamps_rejected():
    frame = bars()
    frame["timestamp"] = frame["timestamp"].dt.tz_localize(None)
    with pytest.raises(ValueError, match="timezone|aware"):
        simulate_trade(frame, 0, Action(1, 1, 1, 1), atr=4)


def test_matrix_preserves_action_order_dtype_and_all_grid_payoffs():
    frame = bars()
    set_bar(frame, 2, 100, 104, 97, 102)
    actions = action_grid()
    actual = payoff_matrix(frame, np.array([0]), np.array([4.0]), actions=actions, cost=1.5)
    expected = [
        simulate_trade(frame, 0, action, atr=4, cost=1.5)["net_points"] for action in actions
    ]
    assert actual.shape == (1, 1080)
    assert actual.dtype == np.float32
    np.testing.assert_allclose(actual[0], expected, atol=1e-6)


def test_matrix_matches_scalar_for_random_paths_gaps_segments_contracts_and_partial_tails():
    rng = np.random.default_rng(20260909)
    frame = bars(200)
    open_ = 100 + np.cumsum(rng.normal(0, 1, 200))
    close = open_ + rng.normal(0, 0.5, 200)
    frame["open"] = open_
    frame["close"] = close
    frame["high"] = np.maximum(open_, close) + rng.uniform(0, 2, 200)
    frame["low"] = np.minimum(open_, close) - rng.uniform(0, 2, 200)
    frame["segment_id"] = np.where(np.arange(200) < 120, 0, 1)
    frame["contract"] = np.where(np.arange(200) < 150, "NQH4", "NQM4")
    frame = frame.drop(index=83)
    indices = np.array([0, 3, 40, 70, 81, 82, 100, 118, 148, 175, 198])
    atrs = np.array([0.375, 4, 2, 3, 8, 4, 2.5, 0.625, 4, 6, 3])
    actions = tuple(
        Action(d, tp, sl, h)
        for d in (1, -1)
        for tp, sl in ((0.5, 2), (3, 0.5), (1, 1))
        for h in (1, 2, 7, 45)
    )
    actual = payoff_matrix(frame, indices, atrs, actions=actions, cost=1.25)
    expected = np.array(
        [
            [
                simulate_trade(frame, int(i), action, float(atr), cost=1.25)["net_points"]
                for action in actions
            ]
            for i, atr in zip(indices, atrs, strict=True)
        ],
        dtype=np.float32,
    )
    np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-6, equal_nan=True)


def test_matrix_retains_closed_before_gap_and_censors_only_longer_unresolved_actions():
    frame = bars(4)
    set_bar(frame, 1, 100, 101, 99.5, 100.5)
    frame = frame.drop(index=2)
    actions = (Action(1, 0.5, 1, 45), Action(1, 2, 1, 45), Action(1, 2, 1, 1))
    actual = payoff_matrix(frame, [0], [2], actions=actions)
    np.testing.assert_allclose(actual[0], [0, np.nan, -0.5], equal_nan=True)


def test_matrix_empty_inputs_have_explicit_shapes():
    frame = bars()
    assert payoff_matrix(frame, [], [], actions=action_grid()).shape == (0, 1080)
    assert payoff_matrix(frame, [0], [4], actions=()).shape == (1, 0)


def test_matrix_rejects_misaligned_or_invalid_inputs():
    with pytest.raises(ValueError):
        payoff_matrix(bars(), [0, 1], [4])
    with pytest.raises(ValueError):
        payoff_matrix(bars(), [0], [0])
    with pytest.raises((IndexError, ValueError)):
        payoff_matrix(bars(), [50], [4])
