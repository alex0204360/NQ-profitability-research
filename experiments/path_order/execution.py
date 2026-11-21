"""Small, event-driven intraday replay for path_order signals."""

from __future__ import annotations

from math import isfinite

import numpy as np
import pandas as pd

POINT_VALUE_USD = 2.0  # one MNQ contract
ENTRY_THRESHOLD_POINTS = 1.5
MINUTE = pd.Timedelta(minutes=1)
FLATTEN_TIME = pd.Timestamp("15:55").time()
TRADE_COLUMNS = [
    "signal_time", "entry_time", "exit_time", "side", "entry", "exit",
    "gross_usd", "net_usd", "reason",
]


def replay(bars: pd.DataFrame, signal: pd.Series, delay: int = 0, cost: float = 3.0):
    """Replay close-generated signals with next-open fills and one MNQ position.

    ``marks`` is a Series named ``equity_usd`` indexed by every bar timestamp.
    It is closing equity: realized net P&L plus the open position's close-marked
    gross P&L less half the round-trip fee while open. The remaining half is
    deducted on exit, so closed equity reflects the full fee exactly once.
    """
    if not isinstance(bars, pd.DataFrame) or not isinstance(signal, pd.Series):
        raise TypeError("bars must be a DataFrame and signal a Series")
    if not bars.index.equals(signal.index):
        raise ValueError("signal index must exactly match bars index")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("bars index must be a timezone-aware DatetimeIndex")
    if str(bars.index.tz) != "America/New_York":
        raise ValueError("bars index must use America/New_York")
    if not bars.index.is_monotonic_increasing or bars.index.has_duplicates:
        raise ValueError("bars index must be strictly increasing")
    if isinstance(delay, (bool, np.bool_)) or not isinstance(delay, (int, np.integer)) or delay not in (0, 1):
        raise ValueError("delay must be 0 or 1")
    cost = float(cost)
    if not isfinite(cost) or cost < 0:
        raise ValueError("cost must be finite and nonnegative")
    needed = {"open", "close"}
    if not needed.issubset(bars.columns):
        raise ValueError("bars must contain open and close columns")
    if len(bars) == 0:
        return pd.DataFrame(columns=TRADE_COLUMNS), pd.Series([], index=bars.index, dtype=float, name="equity_usd")

    opens = bars["open"].to_numpy(dtype=float)
    closes = bars["close"].to_numpy(dtype=float)
    if not np.isfinite(opens).all() or not np.isfinite(closes).all():
        raise ValueError("open and close prices must be finite")
    scores = signal.to_numpy(dtype=float)

    trades = []
    completed_net = 0.0
    position = None
    # Pending order fields are fixed when created; they are never recomputed.
    pending = None
    marks = []

    def close_position(i, price, reason):
        nonlocal position, completed_net
        gross_usd = position["side"] * (float(price) - position["entry"]) * POINT_VALUE_USD
        net_usd = gross_usd - cost
        trades.append({
            "signal_time": position["signal_time"],
            "entry_time": position["entry_time"],
            "exit_time": bars.index[i],
            "side": "long" if position["side"] == 1 else "short",
            "entry": position["entry"],
            "exit": float(price),
            "gross_usd": gross_usd,
            "net_usd": net_usd,
            "reason": reason,
        })
        completed_net += net_usd
        position = None

    for i, timestamp in enumerate(bars.index):
        contiguous = i > 0 and timestamp - bars.index[i - 1] == MINUTE
        if i > 0 and not contiguous:
            # An observation gap invalidates waiting orders. Existing risk is
            # liquidated at the first available open, even across sessions.
            if pending is not None:
                pending = None
            if position is not None:
                close_position(i, opens[i], "gap")

        # Fill only at the immutable due timestamp, and only through contiguous
        # observed minutes. A missing due bar is handled above as a gap.
        if pending is not None:
            if timestamp == pending["due"]:
                order = pending
                pending = None
                if order["kind"] == "entry":
                    if timestamp.time() < FLATTEN_TIME and position is None:
                        position = {
                            "side": order["side"], "entry": opens[i],
                            "signal_time": order["signal_time"], "entry_time": timestamp,
                        }
                elif position is not None:
                    close_position(i, opens[i], "signal")
            elif timestamp > pending["due"]:
                pending = None

        # Scheduled intraday liquidation at 15:55 open. Pending entries are
        # disallowed there; pending exits are superseded by the flatten.
        if timestamp.time() >= FLATTEN_TIME:
            if pending is not None:
                pending = None
            if position is not None:
                close_position(i, opens[i], "time")

        # Decisions occur at this bar's close. Never issue a same-bar flip.
        score = scores[i]
        if pending is None and position is not None:
            if not np.isfinite(score) or score * position["side"] <= 0:
                due = timestamp + (1 + int(delay)) * MINUTE
                if due.time() < FLATTEN_TIME:
                    pending = {"kind": "exit", "due": due}
        elif pending is None and position is None and np.isfinite(score) and abs(score) > ENTRY_THRESHOLD_POINTS:
            due = timestamp + (1 + int(delay)) * MINUTE
            if due.time() < FLATTEN_TIME:
                pending = {"kind": "entry", "due": due, "side": 1 if score > 0 else -1,
                           "signal_time": timestamp}

        floating = (
            0.0
            if position is None
            else position["side"] * (closes[i] - position["entry"]) * POINT_VALUE_USD - cost / 2
        )
        marks.append(completed_net + floating)

    if position is not None:
        raise RuntimeError("final observation ended with an open position")
    trades_frame = pd.DataFrame(trades, columns=TRADE_COLUMNS)
    mark_series = pd.Series(marks, index=bars.index, dtype=float, name="equity_usd")
    return trades_frame, mark_series
