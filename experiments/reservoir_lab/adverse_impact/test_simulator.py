"""Synthetic causal simulator checks; all prices are invented."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from simulator import simulate

REFERENCE = Path(__file__).resolve().parents[2] / "path_order"
sys.path.insert(0, str(REFERENCE))
from execution import replay as original_replay


def bars(times, opens=None, closes=None):
    index = pd.DatetimeIndex(times)
    if index.tz is None:
        index = index.tz_localize("America/New_York")
    n = len(index)
    return pd.DataFrame({
        "open": np.full(n, 100.0) if opens is None else opens,
        "close": np.full(n, 100.0) if closes is None else closes,
        "high": 100.0, "low": 100.0, "volume": 1,
    }, index=index)


def series(values, index):
    return pd.Series(values, index=index, dtype=float)


def test_same_as_original_when_continuation_never_exits_first():
    frame = bars(pd.date_range("2024-01-02 10:00", periods=7, freq="min"),
                 opens=[100, 101, 102, 103, 104, 105, 106],
                 closes=[100, 102, 103, 104, 105, 106, 106])
    raw = series([2, 2, 2, 0, 0, 0, 0], frame.index)
    hold_long = series([1] * len(frame), frame.index)
    hold_short = series([1] * len(frame), frame.index)
    expected, expected_equity = original_replay(frame, raw, cost=6)
    actual, equity, trace = simulate(frame, raw, hold_long, hold_short)
    pd.testing.assert_frame_equal(actual, expected)
    pd.testing.assert_series_equal(equity, expected_equity)
    assert trace.iloc[1:3].notna().all()
    assert trace.iloc[4:].isna().all()


def test_hold_head_exits_next_open_and_reason_is_hold():
    frame = bars(pd.date_range("2024-01-02 10:00", periods=6, freq="min"),
                 opens=[100, 101, 102, 103, 104, 104],
                 closes=[100, 101, 102, 103, 104, 104])
    raw = series([2, 2, 2, 0, 0, 0], frame.index)
    long = series([1, 1, 0, 1, 1, 1], frame.index)
    short = series([1] * 6, frame.index)
    trades, equity, trace = simulate(frame, raw, long, short)
    assert len(trades) == 1
    assert trades.iloc[0].entry_time == frame.index[1]
    assert trades.iloc[0].exit_time == frame.index[3]
    assert trades.iloc[0].reason == "hold"
    assert trades.iloc[0].net_usd == -2  # +4 gross, less $6 round-trip fee
    assert trace.iloc[2] == 0
    assert pd.isna(trace.iloc[3])  # no trace at exit open
    assert equity.iloc[1] == -3  # unchanged close, less half friction
    assert equity.iloc[3] == -2


def test_raw_sign_exit_has_priority_over_hold_head():
    frame = bars(pd.date_range("2024-01-02 10:00", periods=5, freq="min"))
    raw = series([2, 2, -0.1, -0.1, -0.1], frame.index)
    long = series([1] * 5, frame.index)
    short = series([1] * 5, frame.index)
    trades, _, _ = simulate(frame, raw, long, short)
    assert trades.iloc[0].exit_time == frame.index[3]
    assert trades.iloc[0].reason == "signal"


def test_fixed_entries_replay_only_original_entry_and_assert_if_impossible():
    frame = bars(pd.date_range("2024-01-02 10:00", periods=5, freq="min"))
    raw = series([2, 2, 0, 0, 0], frame.index)
    long = series([1] * 5, frame.index)
    short = series([1] * 5, frame.index)
    trades, _, _ = simulate(frame, raw, long, short, fixed_signals={frame.index[0]: 1})
    assert trades.iloc[0].signal_time == frame.index[0]
    with pytest.raises(AssertionError, match="cannot execute"):
        simulate(frame.iloc[:2], raw.iloc[:2], long.iloc[:2], short.iloc[:2],
                 fixed_signals={frame.index[1]: -1})


def test_gap_forces_flatten_and_reports_gap():
    index = ["2024-01-02 10:00", "2024-01-02 10:01", "2024-01-02 10:02", "2024-01-02 10:04", "2024-01-02 10:05"]
    frame = bars(index, opens=[100, 100, 100, 105, 105], closes=[100, 100, 100, 105, 105])
    raw = series([2, 2, 2, 0, 0], frame.index)
    long = series([1] * 5, frame.index)
    short = series([1] * 5, frame.index)
    trades, equity, trace = simulate(frame, raw, long, short)
    assert trades.iloc[0].reason == "gap"
    assert trades.iloc[0].exit_time == frame.index[3]
    assert trades.iloc[0].net_usd == 4
    assert pd.isna(trace.iloc[3])
    assert pd.isna(trace.iloc[4])
    assert equity.iloc[3] == 4


def test_cutoff_flattens_open_trade_and_rejects_fixed_late_entry():
    frame = bars(pd.date_range("2024-01-02 15:52", periods=5, freq="min"))
    raw = series([2, 2, 2, 2, 2], frame.index)
    long = series([1] * 5, frame.index)
    short = series([1] * 5, frame.index)
    trades, _, trace = simulate(frame, raw, long, short)
    assert trades.iloc[0].exit_time == frame.index[3]
    assert trades.iloc[0].reason == "time"
    assert pd.isna(trace.iloc[3])
    with pytest.raises(AssertionError, match="cutoff"):
        simulate(frame, raw, long, short, fixed_signals={frame.index[2]: 1})


def test_short_hold_trace_is_already_signed_and_cutoff_wins_over_exit_signal():
    frame = bars(pd.date_range("2024-01-02 15:51", periods=5, freq="min"))
    raw = series([-2, -2, -2, 2, 2], frame.index)
    long = series([1] * 5, frame.index)
    short = series([0.75, 0.5, 0.25, 0, 0], frame.index)
    trades, _, trace = simulate(frame, raw, long, short)
    assert trace.iloc[1] == 0.5
    assert trace.iloc[2] == 0.25
    assert trace.iloc[3] == 0
    assert pd.isna(trace.iloc[4])
    assert trades.iloc[0].exit_time == frame.index[4]
    assert trades.iloc[0].reason == "time"
