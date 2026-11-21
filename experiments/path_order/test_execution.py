"""Synthetic replay tests; no market data is used."""

import numpy as np
import pandas as pd
import pytest

from execution import replay


def frame(times):
    index = pd.DatetimeIndex(times).tz_localize("America/New_York")
    return pd.DataFrame({"open": 100.0, "close": 100.0, "high": 100.0, "low": 100.0, "volume": 1}, index=index)


def test_entry_exit_price_fee_and_close_marks():
    bars = frame(pd.date_range("2024-01-02 10:00", periods=5, freq="min"))
    bars.loc[bars.index[1], ["open", "close"]] = [101, 102]
    bars.loc[bars.index[3], ["open", "close"]] = [103, 104]
    signal = pd.Series([2.0, 2.0, np.nan, 0.0, 0.0], index=bars.index)
    trades, marks = replay(bars, signal)
    assert list(trades.columns) == ["signal_time", "entry_time", "exit_time", "side", "entry", "exit", "gross_usd", "net_usd", "reason"]
    row = trades.iloc[0]
    assert row.side == "long" and row.entry == 101 and row.exit == 103
    assert row.gross_usd == 4 and row.net_usd == 1 and row.reason == "signal"
    assert marks.iloc[1] == 0.5  # close marked, with half the fee reserved
    assert marks.iloc[3] == 1  # realized net after fee
    assert marks.index.equals(bars.index)


def test_delay_one_and_fixed_pending_entry():
    bars = frame(pd.date_range("2024-01-02 10:00", periods=6, freq="min"))
    bars.loc[bars.index[1], "open"] = 101
    bars.loc[bars.index[2], "open"] = 102
    signal = pd.Series([2, -9, 0, 0, 0, 0], index=bars.index)
    trades, _ = replay(bars, signal, delay=1)
    assert trades.iloc[0].entry_time == bars.index[2]
    assert trades.iloc[0].entry == 102


def test_threshold_is_strict_and_sign_controls_side():
    bars = frame(pd.date_range("2024-01-02 10:00", periods=4, freq="min"))
    signal = pd.Series([1.5, -2, 0, 0], index=bars.index)
    trades, _ = replay(bars, signal)
    assert trades.iloc[0].side == "short"
    assert trades.iloc[0].signal_time == bars.index[1]


def test_gap_cancels_pending_entry_and_forces_existing_position_exit():
    times = ["2024-01-02 10:00", "2024-01-02 10:01", "2024-01-02 10:02", "2024-01-02 10:04", "2024-01-02 10:05"]
    bars = frame(times)
    bars.loc[bars.index[3], ["open", "close"]] = [105, 106]
    signal = pd.Series([2, 2, 2, 0, np.nan], index=bars.index)
    trades, marks = replay(bars, signal)
    assert trades.iloc[0].entry_time == bars.index[1]
    assert trades.iloc[0].exit_time == bars.index[3]
    assert trades.iloc[0].reason == "gap"
    assert trades.iloc[0].net_usd == 7
    assert marks.iloc[3] == 7


def test_pending_entry_is_cancelled_by_gap():
    times = ["2024-01-02 10:00", "2024-01-02 10:02", "2024-01-02 10:03"]
    bars = frame(times)
    signal = pd.Series([3, 0, 0], index=bars.index)
    trades, marks = replay(bars, signal)
    assert trades.empty and (marks == 0).all()


def test_flatten_at_1555_and_no_entry_at_or_after_boundary():
    times = pd.date_range("2024-01-02 15:52", periods=5, freq="min")
    bars = frame(times)
    bars.loc[bars.index[3], "open"] = 99
    signal = pd.Series([2, 2, 2, 2, 2], index=bars.index)
    trades, _ = replay(bars, signal)
    assert len(trades) == 1
    assert trades.iloc[0].entry_time == bars.index[1]
    assert trades.iloc[0].exit_time == bars.index[3]
    assert trades.iloc[0].reason == "time"


def test_position_open_at_final_observation_is_hard_error():
    bars = frame(pd.date_range("2024-01-02 10:00", periods=2, freq="min"))
    signal = pd.Series([2, 2], index=bars.index)
    with pytest.raises(RuntimeError, match="open position"):
        replay(bars, signal)
