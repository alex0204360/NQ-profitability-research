import numpy as np
import pandas as pd

from tools.causal_execution import replay_causal as replay_v2
from tools.causal_execution_v3 import replay_causal as replay_v3


def test_selected_ten_bar_horizon_matches_frozen_execution():
    times = pd.date_range("2026-10-01", periods=35, freq="min", tz="UTC")
    bars = pd.DataFrame({"timestamp": times, "open": 25000 + np.arange(35) * .25,
                         "high": 25001 + np.arange(35) * .25,
                         "low": 24999 + np.arange(35) * .25,
                         "close": 25000.25 + np.arange(35) * .25,
                         "volume": np.full(35, 100)})
    signal = np.zeros(35, dtype=int)
    signal[10] = 1
    atr = np.full(35, 2.0)
    cost = {"commission_per_side": 2.0, "slippage_ticks_per_side": 2}
    old, old_trades, _ = replay_v2(bars, signal, atr, times[0], times[-1] + pd.Timedelta(minutes=1), "time10", cost)
    new, new_trades, _ = replay_v3(bars, signal, atr, times[0], times[-1] + pd.Timedelta(minutes=1), "time10", cost, holding_bars=np.full(35, 10))
    assert old["net"] == new["net"] and old["trades"] == new["trades"]
    assert old_trades[0]["exit_time"] == new_trades[0]["exit_time"]


def test_selected_three_bar_exit_is_frozen_at_signal_time():
    times = pd.date_range("2026-10-01", periods=35, freq="min", tz="UTC")
    bars = pd.DataFrame({"timestamp": times, "open": np.full(35, 25000.),
                         "high": np.full(35, 25001.), "low": np.full(35, 24999.),
                         "close": np.full(35, 25000.25), "volume": np.full(35, 100)})
    signal = np.zeros(35, dtype=int)
    signal[10] = 1
    horizon = np.full(35, 10)
    horizon[10] = 3
    _, trades, _ = replay_v3(bars, signal, np.full(35, 2.), times[0], times[-1] + pd.Timedelta(minutes=1), "time10", {"commission_per_side": 1.5, "slippage_ticks_per_side": 1}, holding_bars=horizon)
    assert trades[0]["planned_horizon"] == 3
    assert trades[0]["held_bars"] == 3
