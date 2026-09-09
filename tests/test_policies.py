"""Preregistered policy learning and frozen-encoder behavior on synthetic data."""

import json

import numpy as np
import pandas as pd
import pytest

from nqprofit.policies import encode_states, fit_encoder, fit_policy, select_action


FEATURES = [
    "price_z20", "trend20_60", "body_fraction", "upper_wick_fraction",
    "lower_wick_fraction", "lag1_return_to_range", "range_to_atr14",
    "volume_z20", "range_z20", "position60",
]


def action(name="a", horizon=5, direction=1, tp=1.0, sl=1.0):
    return {"action_id": name, "direction": direction, "tp_atr": tp,
            "sl_atr": sl, "horizon": horizon}


def synthetic_features(n=80):
    rng = np.random.default_rng(44)
    frame = pd.DataFrame(rng.normal(size=(n, len(FEATURES))), columns=FEATURES)
    frame["atr14_fraction"] = np.linspace(0.001, 0.003, n)
    timestamps = pd.date_range("2023-01-03 00:00", periods=n, freq="5min", tz="UTC")
    return frame, timestamps


def sample_days(n_days=20, n_per_day=10):
    return np.repeat(pd.date_range("2023-01-01", periods=n_days).strftime("%Y-%m-%d"), n_per_day)


@pytest.mark.parametrize("family,n_states", [("regime8", 8), ("regime16", 16)])
def test_regime_encoder_freezes_median_and_round_trips(family, n_states):
    features, timestamps = synthetic_features()
    encoder = fit_encoder(features, timestamps, family)
    assert encoder["n_states"] == n_states
    assert encoder["volatility_median"] == pytest.approx(0.002)
    restored = json.loads(json.dumps(encoder, allow_nan=False))
    expected = encode_states(features, timestamps, restored)
    assert expected.dtype == np.int64
    assert np.all((expected >= 0) & (expected < n_states))
    future = features.copy()
    future.loc[40:, "atr14_fraction"] = 1e6
    actual = encode_states(future, timestamps, restored)
    np.testing.assert_array_equal(expected[:40], actual[:40])
    assert restored == encoder


def test_regime_close_time_buckets_use_eastern_dst_and_boundary_rules():
    fit, fit_ts = synthetic_features()
    test = pd.DataFrame({"trend20_60": [0.0] * 8, "atr14_fraction": [0.002] * 8})
    timestamps = pd.DatetimeIndex([
        "2023-07-03T03:59:00Z", "2023-07-03T04:00:00Z",
        "2023-07-03T10:00:00Z", "2023-07-03T13:29:00Z",
        "2023-07-03T13:30:00Z", "2023-07-03T19:59:00Z",
        "2023-07-03T20:00:00Z", "2023-01-03T14:30:00Z",
    ])
    # Median equality belongs to the lower-volatility state; zero trend is nonnegative.
    np.testing.assert_array_equal(
        encode_states(test, timestamps, fit_encoder(fit, fit_ts, "regime16")),
        [14, 2, 6, 6, 10, 10, 14, 10],
    )
    np.testing.assert_array_equal(
        encode_states(test, timestamps, fit_encoder(fit, fit_ts, "regime8")),
        [2, 2, 2, 2, 6, 6, 2, 6],
    )


def test_regime_trend_and_volatility_flags_are_separate():
    fit, fit_ts = synthetic_features()
    test = pd.DataFrame({"trend20_60": [-1, -1, 0, 1], "atr14_fraction": [.001, .003, .001, .003]})
    ts = pd.DatetimeIndex(["2023-07-03T14:00:00Z"] * 4)
    np.testing.assert_array_equal(encode_states(test, ts, fit_encoder(fit, fit_ts, "regime8")), [4, 5, 6, 7])


@pytest.mark.parametrize("family,k", [("prototype8", 8), ("prototype16", 16)])
def test_prototype_fit_is_deterministic_serializable_and_uses_population_scale(family, k):
    features, timestamps = synthetic_features()
    features["body_fraction"] = 0.5  # Constant columns use scale=1, as StandardScaler.
    encoder = fit_encoder(features, timestamps, family)
    assert encoder == fit_encoder(features, timestamps, family)
    assert encoder["feature_columns"] == FEATURES
    np.testing.assert_allclose(encoder["scaler_mean"], features[FEATURES].mean(axis=0))
    expected_scale = features[FEATURES].std(axis=0, ddof=0).to_numpy()
    expected_scale[expected_scale == 0] = 1
    np.testing.assert_allclose(encoder["scaler_scale"], expected_scale)
    assert np.asarray(encoder["centroids"]).shape == (k, 10)
    restored = json.loads(json.dumps(encoder, allow_nan=False))
    values = (features[FEATURES].to_numpy() - encoder["scaler_mean"]) / encoder["scaler_scale"]
    expected = ((values[:, None, :] - np.asarray(encoder["centroids"])[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
    np.testing.assert_array_equal(encode_states(features, timestamps, restored), expected)
    np.testing.assert_array_equal(encode_states(features.iloc[:7], timestamps[:7], restored), expected[:7])
    assert restored == encoder


def test_encoder_rejects_bad_family_missing_nonfinite_and_naive_inputs():
    features, timestamps = synthetic_features()
    with pytest.raises(ValueError):
        fit_encoder(features, timestamps, "future_predictor")
    with pytest.raises(ValueError):
        fit_encoder(features.drop(columns="price_z20"), timestamps, "prototype8")
    with pytest.raises(ValueError):
        fit_encoder(features, timestamps.tz_localize(None), "regime8")
    with pytest.raises(ValueError):
        fit_encoder(features, timestamps[:-1], "regime8")
    features.loc[0, "price_z20"] = np.inf
    with pytest.raises(ValueError):
        fit_encoder(features, timestamps, "prototype8")
    with pytest.raises(ValueError):
        fit_encoder(features.iloc[:3], timestamps[:3], "prototype16")


def test_empty_inference_returns_empty_integer_array():
    features, timestamps = synthetic_features()
    for family in ["regime8", "prototype8"]:
        encoder = fit_encoder(features, timestamps, family)
        states = encode_states(features.iloc[:0], timestamps[:0], encoder)
        assert states.size == 0
        assert states.dtype == np.int64


def test_day_cluster_shrinkage_uses_dates_not_independent_trade_standard_error():
    days = np.tile(sample_days(), 2)
    states = np.repeat([0, 1], 200)
    noise = np.repeat(np.tile([-1.0, 1.0], 10), 10)
    payoffs = np.concatenate([1 + noise, 5 + noise])[:, None]
    model = fit_policy(states, days, payoffs, policy_id="regime8", n_states=2, actions=[action()])
    expected_se = 1 / np.sqrt(19)
    assert model["global"]["mean_net_points"] == pytest.approx([3])
    assert model["global"]["standard_errors"] == pytest.approx([expected_se])
    assert model["states"][0]["predicted_net_points"] == pytest.approx([2])
    assert model["states"][1]["predicted_net_points"] == pytest.approx([4])
    assert model["states"][0]["ranking_scores"] == pytest.approx([2 - expected_se])
    assert model["states"][1]["ranking_scores"] == pytest.approx([4 - expected_se])
    selected = select_action(json.loads(json.dumps(model, allow_nan=False)), 0)
    assert selected["predicted_net_points"] == pytest.approx(2)
    assert selected["sample_size"] == 200
    assert selected["date_count"] == 20
    assert selected["action_index"] == 0


def test_day_cluster_se_handles_unequal_daily_counts_and_order_independently():
    # Twenty daily clusters, unequal numbers of identical within-day payoffs.
    counts = np.arange(1, 21)
    days = np.repeat(pd.date_range("2023-01-01", periods=20).strftime("%Y-%m-%d"), counts)
    y = np.repeat(np.arange(1.0, 21.0), counts)
    mean = y.mean()
    expected_se = np.sqrt(20 / 19 * np.sum((counts * (np.arange(1.0, 21.0) - mean)) ** 2)) / len(y)
    model = fit_policy(np.zeros(len(y), dtype=int), days, y[:, None], policy_id="p", n_states=1, actions=[action()])
    assert model["global"]["standard_errors"] == pytest.approx([expected_se])
    order = np.random.default_rng(91).permutation(len(y))
    shuffled = fit_policy(np.zeros(len(y), dtype=int), days[order], y[order, None], policy_id="p", n_states=1, actions=[action()])
    assert shuffled["global"]["ranking_scores"] == pytest.approx(model["global"]["ranking_scores"])


@pytest.mark.parametrize("n_days,n_per_day", [(19, 20), (20, 9)])
def test_state_abstains_below_either_minimum_support(n_days, n_per_day):
    days = sample_days(n_days, n_per_day)
    model = fit_policy(np.zeros(len(days), dtype=int), days, np.full((len(days), 1), 100.0), policy_id="p", n_states=2, actions=[action()])
    assert select_action(model, 0) is None
    assert select_action(model, 1) is None
    assert model["states"][0]["supported"] is False
    json.dumps(model, allow_nan=False)


def test_unsupported_state_does_not_fall_back_to_profitable_global():
    days = np.concatenate([sample_days(), np.array(["2023-02-01"])])
    states = np.concatenate([np.zeros(200, dtype=int), [1]])
    model = fit_policy(states, days, np.full((201, 1), 8.0), policy_id="p", n_states=2, actions=[action()])
    assert select_action(model, 0) is not None
    assert select_action(model, 1) is None
    model["policy_id"] = "unconditional"
    assert select_action(model, 1)["sample_size"] == 201


def test_no_positive_action_abstains_and_input_model_is_not_mutated():
    for payoff in [-10.0, 0.0]:
        model = fit_policy(np.zeros(200, dtype=int), sample_days(), np.full((200, 1), payoff), policy_id="p", n_states=1, actions=[action()])
        before = json.dumps(model)
        assert select_action(model, 0) is None
        assert json.dumps(model) == before


def test_calendar_feasibility_is_applied_before_ranking():
    actions = [action("long", 45), action("short", 1)]
    model = fit_policy(np.zeros(200, dtype=int), sample_days(), np.tile([10.0, 1.0], (200, 1)), policy_id="p", n_states=1, actions=actions)
    assert select_action(model, 0)["action_id"] == "long"
    assert select_action(model, 0, max_horizon=2)["action_id"] == "short"
    assert select_action(model, 0, max_horizon=0) is None
    selected = select_action(model, 0)
    selected["horizon"] = 99
    assert model["actions"][0]["horizon"] == 45


def test_equal_scores_tie_break_by_horizon_stop_target_then_long():
    actions = [action("large_target", 1, -1, 2, .5), action("short", 1, -1, .5, .5),
               action("long", 1, 1, .5, .5), action("large_stop", 1, 1, .5, 2),
               action("long_hold", 2, 1, .5, .5)]
    model = fit_policy(np.zeros(200, dtype=int), sample_days(), np.ones((200, len(actions))), policy_id="p", n_states=1, actions=actions)
    assert select_action(model, 0)["action_id"] == "long"


def test_zero_row_fit_is_serializable_and_abstains():
    model = fit_policy(np.array([], dtype=int), np.array([], dtype=str), np.empty((0, 1)), policy_id="p", n_states=1, actions=[action()])
    assert select_action(model, 0) is None
    json.dumps(model, allow_nan=False)


@pytest.mark.parametrize("change", ["nan", "shape", "state_float", "state_range", "days_shape", "empty_day", "action_horizon", "action_direction"])
def test_invalid_policy_training_inputs_fail_closed(change):
    states = np.zeros(200, dtype=int)
    days = sample_days()
    payoffs = np.ones((200, 1))
    actions = [action()]
    if change == "nan":
        payoffs[0, 0] = np.nan
    elif change == "shape":
        payoffs = np.ones(200)
    elif change == "state_float":
        states = states.astype(float) + .5
    elif change == "state_range":
        states[0] = 1
    elif change == "days_shape":
        days = days[:-1]
    elif change == "empty_day":
        days[0] = ""
    elif change == "action_horizon":
        actions[0]["horizon"] = 46
    elif change == "action_direction":
        actions[0]["direction"] = 0
    with pytest.raises(ValueError):
        fit_policy(states, days, payoffs, policy_id="p", n_states=1, actions=actions)


def test_selection_rejects_invalid_state_and_scope():
    model = fit_policy(np.zeros(200, dtype=int), sample_days(), np.ones((200, 1)), policy_id="p", n_states=1, actions=[action()])
    for state in [-1, 1, .5]:
        with pytest.raises(ValueError):
            select_action(model, state)
    with pytest.raises(ValueError):
        select_action(model, 0, max_horizon=46)
