"""Policy occupancy and calendar correctness; synthetic bars are not profit evidence."""

import numpy as np
import pandas as pd

from nqprofit.replay import complete_future, decision_indices, feasible_horizons, replay_policy


def bars(n=100):
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-02T10:00Z", periods=n, freq="min"),
            "open": 100.0,
            "high": 100.25,
            "low": 99.75,
            "close": 100.0,
            "volume": 1,
            "segment_id": 0,
        }
    )


def model(horizon=6):
    action = {
        "direction": 1,
        "tp_atr": 3.0,
        "sl_atr": 2.0,
        "horizon": horizon,
        "action_id": "fixture",
    }
    table = {
        "supported": True,
        "sample_size": 300,
        "date_count": 30,
        "predicted_net_points": [2.0],
        "ranking_scores": [1.0],
    }
    return {
        "policy_id": "fixture",
        "n_states": 1,
        "actions": [action],
        "states": [table],
        "global": table,
    }


def test_decision_clock_is_completed_close_and_feature_valid():
    frame = bars()
    features = pd.DataFrame({"valid": np.arange(100) >= 60})
    assert decision_indices(frame, features).tolist() == [64, 69, 74, 79, 84, 89, 94, 99]


def test_future_completeness_resets_at_gap_and_segment():
    frame = bars()
    assert complete_future(frame, np.array([0, 54, 55, 99]), 45).tolist() == [
        True,
        True,
        False,
        False,
    ]
    frame.loc[30:, "segment_id"] = 1
    assert complete_future(frame, np.array([0, 30]), 45).tolist() == [False, True]
    frame = bars().drop(index=30).reset_index(drop=True)
    assert not complete_future(frame, np.array([0]), 45)[0]


def test_calendar_spans_known_breaks_and_period_end():
    frame = bars()
    schedule = pd.DataFrame(
        {
            "market_open": [pd.Timestamp("2024-01-02T10:00Z")],
            "break_start": [pd.Timestamp("2024-01-02T10:30Z")],
            "break_end": [pd.Timestamp("2024-01-02T10:40Z")],
            "market_close": [pd.Timestamp("2024-01-02T11:30Z")],
        }
    )
    out = feasible_horizons(frame, schedule, pd.Timestamp("2024-01-02T11:00Z"))
    assert out[24] == 5 and out[29] == 0 and out[34] == 0
    assert out[39] == 20 and out[54] == 5 and out[59] == 0


def test_position_blocks_overlapping_decisions_until_actual_exit():
    frame = bars(30)
    features = pd.DataFrame({"valid": True, "atr14": 1.0}, index=frame.index)
    result = replay_policy(
        frame,
        features,
        np.array([4, 9, 14, 19, 24]),
        np.full(30, 45),
        np.zeros(30, dtype=int),
        model(),
    )
    assert [t["detection_index"] for t in result["trades"]] == [4, 14, 24]
    assert result["trades"][-1]["exit_reason"] == "censored"
    assert result["occupied_decisions"] == 2


def test_evaluation_keeps_early_exit_before_future_gap():
    frame = bars(12)
    frame.loc[5, "high"] = 104
    features = pd.DataFrame({"valid": True, "atr14": 1.0}, index=frame.index)
    result = replay_policy(
        frame, features, np.array([4]), np.full(12, 45), np.zeros(12, dtype=int), model(45)
    )
    assert len(result["trades"]) == 1
    assert result["trades"][0]["exit_reason"] == "tp"
    assert result["trades"][0]["resolution_bars"] == 1


def test_known_close_infeasible_action_abstains_without_peeking():
    frame = bars(12)
    features = pd.DataFrame({"valid": True, "atr14": 1.0}, index=frame.index)
    result = replay_policy(
        frame, features, np.array([4]), np.full(12, 3), np.zeros(12, dtype=int), model(6)
    )
    assert result["trades"] == []
    assert result["abstained_decisions"] == 1
