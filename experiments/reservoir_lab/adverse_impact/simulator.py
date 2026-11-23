"""Causal simulator for already-open continuation heads."""

from __future__ import annotations

from math import isfinite

import numpy as np
import pandas as pd

POINT_VALUE_USD = 2.0
ENTRY_THRESHOLD_POINTS = 1.5
FRICTION_USD = 6.0
MINUTE = pd.Timedelta(minutes=1)
FLATTEN_TIME = pd.Timestamp("15:55").time()
TRADE_COLUMNS = [
    "signal_time", "entry_time", "exit_time", "side", "entry", "exit",
    "gross_usd", "net_usd", "reason",
]


def simulate(bars, raw, hold_long, hold_short, fixed_signals=None):
    """Simulate entries and side-specific continuation exits on one NY session.

    All signals are known at their bar close and fill at the next contiguous
    observed open. ``fixed_signals`` replaces normal raw-threshold entries with
    a mapping of original signal timestamps to sides (+1/-1). It never fixes
    exits. Equity is close-marked, reserving half the $6 friction while open;
    the remaining half is realized on exit. The signed continuation value at
    each bar close is returned in ``hold_trace`` only while holding a position.
    """
    if not isinstance(bars, pd.DataFrame) or not all(
        isinstance(series, pd.Series) for series in (raw, hold_long, hold_short)
    ):
        raise TypeError("bars must be a DataFrame and signals must be Series")
    for series in (raw, hold_long, hold_short):
        if not bars.index.equals(series.index):
            raise ValueError("all signal indexes must exactly match bars")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("bars index must be timezone-aware")
    if str(bars.index.tz) != "America/New_York":
        raise ValueError("bars index must use America/New_York")
    if not bars.index.is_monotonic_increasing or bars.index.has_duplicates:
        raise ValueError("bars index must be strictly increasing")
    if len(bars) and len(set(bars.index.date)) != 1:
        raise ValueError("simulate one New York session at a time")
    if not {"open", "close"}.issubset(bars.columns):
        raise ValueError("bars must contain open and close columns")
    if fixed_signals is not None and not hasattr(fixed_signals, "items"):
        raise TypeError("fixed_signals must be a mapping of timestamps to sides")

    opened = bars["open"].to_numpy(dtype=float)
    closed = bars["close"].to_numpy(dtype=float)
    if not np.isfinite(opened).all() or not np.isfinite(closed).all():
        raise ValueError("open and close prices must be finite")
    raw_values = raw.to_numpy(dtype=float)
    long_values = hold_long.to_numpy(dtype=float)
    short_values = hold_short.to_numpy(dtype=float)

    fixed_by_pos = {}
    if fixed_signals is not None:
        for timestamp, side in fixed_signals.items():
            timestamp = pd.Timestamp(timestamp)
            if timestamp.tzinfo is None:
                raise ValueError("fixed signal timestamps must be timezone-aware")
            timestamp = timestamp.tz_convert(bars.index.tz)
            if timestamp not in bars.index:
                raise AssertionError(f"fixed entry timestamp is not present in bars: {timestamp}")
            if isinstance(side, (bool, np.bool_)) or side not in (-1, 1):
                raise ValueError("fixed signal sides must be +1 or -1")
            pos = bars.index.get_loc(timestamp)
            fixed_by_pos[int(pos)] = int(side)

    trades = []
    equity_values = []
    trace_values = []
    realized_net = 0.0
    position = None
    pending = None
    consumed_fixed = set()

    def exit_at(i, price, reason):
        nonlocal position, realized_net
        gross = position["side"] * (float(price) - position["entry"]) * POINT_VALUE_USD
        net = gross - FRICTION_USD
        trades.append({
            "signal_time": position["signal_time"],
            "entry_time": position["entry_time"],
            "exit_time": bars.index[i],
            "side": "long" if position["side"] == 1 else "short",
            "entry": position["entry"],
            "exit": float(price),
            "gross_usd": gross,
            "net_usd": net,
            "reason": reason,
        })
        realized_net += net
        position = None

    for i, timestamp in enumerate(bars.index):
        contiguous = i > 0 and timestamp - bars.index[i - 1] == MINUTE
        if i and not contiguous:
            if pending is not None:
                if pending["kind"] == "entry" and pending.get("fixed", False):
                    raise AssertionError(f"fixed entry could not execute after observation gap: {pending['signal_time']}")
                pending = None
            if position is not None:
                exit_at(i, opened[i], "gap")

        exit_open = False
        if pending is not None:
            if timestamp == pending["due"]:
                order = pending
                pending = None
                if order["kind"] == "entry":
                    if timestamp.time() >= FLATTEN_TIME or position is not None:
                        if order.get("fixed", False):
                            raise AssertionError(f"fixed entry could not execute: {order['signal_time']}")
                    else:
                        position = {
                            "side": order["side"], "entry": opened[i],
                            "signal_time": order["signal_time"], "entry_time": timestamp,
                        }
                elif position is not None:
                    exit_at(i, opened[i], order["reason"])
                    exit_open = True
            elif timestamp > pending["due"]:
                order = pending
                pending = None
                if order["kind"] == "entry" and order.get("fixed", False):
                    raise AssertionError(f"fixed entry could not execute: {order['signal_time']}")

        if timestamp.time() >= FLATTEN_TIME:
            if pending is not None:
                order = pending
                pending = None
                if order["kind"] == "entry" and order.get("fixed", False):
                    raise AssertionError(f"fixed entry cannot execute at/after cutoff: {order['signal_time']}")
            if position is not None:
                exit_at(i, opened[i], "time")
                exit_open = True

        # Record continuation at close only for a position held through this
        # bar. Exit-open bars have no holding trace, even though they have a close.
        held_at_close = position is not None and not exit_open
        side = position["side"] if held_at_close else 0
        continuation = long_values[i] if side == 1 else short_values[i] if side == -1 else np.nan
        trace_values.append(continuation if side else np.nan)

        if held_at_close and pending is None:
            raw_score = raw_values[i]
            if not np.isfinite(raw_score) or raw_score * side <= 0:
                due = timestamp + MINUTE
                if due.time() < FLATTEN_TIME:
                    pending = {"kind": "exit", "due": due, "reason": "signal"}
            elif not np.isfinite(continuation) or continuation <= 0:
                due = timestamp + MINUTE
                if due.time() < FLATTEN_TIME:
                    pending = {"kind": "exit", "due": due, "reason": "hold"}
        elif not held_at_close and position is None and pending is None:
            if fixed_signals is None:
                score = raw_values[i]
                if np.isfinite(score) and abs(score) > ENTRY_THRESHOLD_POINTS:
                    due = timestamp + MINUTE
                    if due.time() < FLATTEN_TIME:
                        pending = {"kind": "entry", "due": due,
                                   "side": 1 if score > 0 else -1, "signal_time": timestamp}
            elif i in fixed_by_pos:
                due = timestamp + MINUTE
                if due.time() >= FLATTEN_TIME or i + 1 >= len(bars):
                    raise AssertionError(f"fixed entry cannot execute after cutoff/end: {timestamp}")
                pending = {"kind": "entry", "due": due, "side": fixed_by_pos[i],
                           "signal_time": timestamp, "fixed": True}
                consumed_fixed.add(i)

        floating = 0.0
        if position is not None:
            floating = position["side"] * (closed[i] - position["entry"]) * POINT_VALUE_USD - FRICTION_USD / 2
        equity_values.append(realized_net + floating)

    if position is not None:
        raise RuntimeError("final observation ended with an open position")
    if fixed_signals is not None and consumed_fixed != set(fixed_by_pos):
        missed = sorted(set(fixed_by_pos) - consumed_fixed)
        raise AssertionError(f"fixed entries could not be scheduled at positions {missed}")
    trades = pd.DataFrame(trades, columns=TRADE_COLUMNS)
    equity = pd.Series(equity_values, index=bars.index, dtype=float, name="equity_usd")
    hold_trace = pd.Series(trace_values, index=bars.index, dtype=float, name="hold_trace")
    return trades, equity, hold_trace
