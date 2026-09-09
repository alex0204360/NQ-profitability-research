"""Bounded, conservative OHLC execution and vectorized action payoffs.

Bars are completed one-minute bars with interval-start timestamps. An action is
decided at a detection bar's close and enters at the next contiguous bar's open.
No exchange calendar is inferred here: callers filter known scheduled closures.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import floor, isfinite
from numbers import Integral

import numpy as np
import pandas as pd

TICK_SIZE = 0.25
MAX_HORIZON = 45
MINUTE = pd.Timedelta(minutes=1)
_PRICE_COLUMNS = ("open", "high", "low", "close")


@dataclass(frozen=True)
class Action:
    """A target and stop fixed before entry, with an integer minute cap."""

    direction: int
    tp_atr: float
    sl_atr: float
    horizon: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.horizon, (bool, np.bool_))
            or not isinstance(self.horizon, Integral)
            or not 1 <= self.horizon <= MAX_HORIZON
        ):
            raise ValueError("rejected — out of scope: horizon must be an integer from 1 to 45")
        if (
            isinstance(self.direction, (bool, np.bool_))
            or not isinstance(self.direction, Integral)
            or self.direction not in (-1, 1)
        ):
            raise ValueError("direction must be +1 (long) or -1 (short)")
        for name in ("tp_atr", "sl_atr"):
            value = _positive_float(getattr(self, name), name)
            object.__setattr__(self, name, value)
        object.__setattr__(self, "direction", int(self.direction))
        object.__setattr__(self, "horizon", int(self.horizon))

    @property
    def action_id(self) -> str:
        side = "long" if self.direction == 1 else "short"
        return f"{side}_tp{self.tp_atr}_sl{self.sl_atr}_h{self.horizon:02d}"


def _positive_float(value: float, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be positive and finite") from error
    if isinstance(value, (bool, np.bool_)) or not isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return number


def action_grid() -> tuple[Action, ...]:
    """All 1,080 actions in the preregistered ranking tie-break order."""
    return tuple(
        Action(direction, tp, sl, horizon)
        for horizon in range(1, MAX_HORIZON + 1)
        for sl in (0.5, 1.0, 2.0)
        for tp in (0.5, 1.0, 2.0, 3.0)
        for direction in (1, -1)
    )


def quantize_distance(atr: float, multiple: float) -> float:
    """Round a positive ATR distance half-up to ticks, with a one-tick minimum."""
    distance = _positive_float(atr, "atr") * _positive_float(multiple, "multiple")
    if not isfinite(distance / TICK_SIZE):
        raise ValueError("distance is too large")
    return max(1, floor(distance / TICK_SIZE + 0.5)) * TICK_SIZE


def _cost(value: float) -> float:
    value = float(value)
    if not isfinite(value) or value < 0:
        raise ValueError("cost must be finite and nonnegative")
    return value


def _check_index(index: int, count: int) -> int:
    if isinstance(index, (bool, np.bool_)) or not isinstance(index, Integral):
        raise TypeError("detection_index must be a positional integer")
    if index < 0 or index >= count:
        raise IndexError("detection_index is outside bars")
    return int(index)


def _timestamp(value) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise ValueError("timestamp must be finite and timezone-aware")
    return timestamp.tz_convert("UTC")


def _same_identifier(left, right) -> bool:
    return not (pd.isna(left) or pd.isna(right)) and bool(left == right)


def _valid_prices(open_: float, high: float, low: float, close: float) -> bool:
    return (
        isfinite(open_)
        and isfinite(high)
        and isfinite(low)
        and isfinite(close)
        and high >= max(open_, close)
        and low <= min(open_, close)
    )


def simulate_trade(
    bars: pd.DataFrame,
    detection_index: int,
    action: Action,
    atr: float,
    cost: float = 1.0,
) -> dict:
    """Price one attempted trade, or return a censored result without P&L.

    ``detection_index`` is positional, independent of the DataFrame's index.
    Exits are conservatively recorded at the resolving bar's close, including
    opening-gap fills. Censored attempts retain the originally planned expiry.
    Already observed exits do not depend on completeness of unused future bars.
    """
    if not isinstance(action, Action):
        raise TypeError("action must be an Action")
    index = _check_index(detection_index, len(bars))
    cost = _cost(cost)
    tp = quantize_distance(atr, action.tp_atr)
    sl = quantize_distance(atr, action.sl_atr)
    timestamps = bars["timestamp"].array
    detected = _timestamp(timestamps[index])
    entry_time = detected + MINUTE
    expiry = entry_time + action.horizon * MINUTE
    result = {
        "detection_index": index,
        "entry_time": entry_time.isoformat(),
        "exit_time": expiry.isoformat(),
        "direction": action.direction,
        "tp_points": tp,
        "sl_points": sl,
        "horizon": action.horizon,
        "action_id": action.action_id,
        "entry_price": None,
        "exit_price": None,
        "exit_reason": "censored",
        "ambiguous": False,
        "resolution_bars": None,
        "gross_points": None,
        "net_points": None,
    }
    prices = [bars[column].to_numpy(copy=False) for column in _PRICE_COLUMNS]
    identifiers = [
        bars[column].to_numpy(copy=False)
        for column in ("segment_id", "contract")
        if column in bars.columns
    ]
    direction = action.direction
    entry = None
    for offset in range(1, action.horizon + 1):
        position = index + offset
        if position >= len(bars):
            return result
        time = _timestamp(timestamps[position])
        if time != detected + offset * MINUTE:
            return result
        if any(not _same_identifier(values[index], values[position]) for values in identifiers):
            return result
        open_, high, low, close = (float(values[position]) for values in prices)
        if not _valid_prices(open_, high, low, close):
            return result
        if entry is None:
            entry = open_
            target = entry + direction * tp
            stop = entry - direction * sl
            result["entry_price"] = entry
        target_open = direction * (open_ - target) >= 0
        stop_open = direction * (open_ - stop) <= 0
        target_touch = high >= target if direction == 1 else low <= target
        stop_touch = low <= stop if direction == 1 else high >= stop
        ambiguous = False
        if stop_open:
            reason, exit_price = "sl", open_
        elif target_open:
            reason, exit_price = "tp", target
        elif stop_touch:
            reason, exit_price = "sl", stop
            ambiguous = bool(target_touch)
        elif target_touch:
            reason, exit_price = "tp", target
        elif offset == action.horizon:
            reason, exit_price = "timeout", close
        else:
            continue
        gross = direction * (exit_price - entry)
        result.update(
            {
                "exit_time": (time + MINUTE).isoformat(),
                "exit_price": exit_price,
                "exit_reason": reason,
                "ambiguous": ambiguous,
                "resolution_bars": offset,
                "gross_points": gross,
                "net_points": gross - cost,
            }
        )
        return result
    return result  # pragma: no cover - positive horizons return on expiry or earlier.


def _matrix_inputs(bars, indices, atr_values, cost):
    cost = _cost(cost)
    indices = np.asarray(indices)
    atr_values = np.asarray(atr_values, dtype=np.float64)
    if indices.ndim != 1 or atr_values.ndim != 1 or len(indices) != len(atr_values):
        raise ValueError("indices and atr_values must be equally sized one-dimensional arrays")
    if len(indices) and not np.issubdtype(indices.dtype, np.integer):
        raise ValueError("indices must contain positional integers")
    indices = indices.astype(np.int64)
    if np.any(indices < 0) or np.any(indices >= len(bars)):
        raise IndexError("detection index is outside bars")
    if not np.all(np.isfinite(atr_values) & (atr_values > 0)):
        raise ValueError("atr_values must be positive and finite")
    return indices, atr_values, cost


def _available_bars(bars: pd.DataFrame, indices: np.ndarray, prices) -> np.ndarray:
    timestamps = pd.DatetimeIndex(bars["timestamp"])
    if timestamps.tz is None or timestamps.hasnans:
        raise ValueError("timestamp must be finite and timezone-aware")
    stamps = timestamps.as_unit("ns").asi8
    open_, high, low, close = prices
    valid = (
        np.isfinite(open_)
        & np.isfinite(high)
        & np.isfinite(low)
        & np.isfinite(close)
        & (high >= np.maximum(open_, close))
        & (low <= np.minimum(open_, close))
    )
    connected = np.zeros(len(bars), dtype=bool)
    connected[1:] = (np.diff(stamps) == MINUTE.value) & valid[1:]
    for column in ("segment_id", "contract"):
        if column in bars.columns:
            values = bars[column].to_numpy(copy=False)
            connected[1:] &= (
                (values[1:] == values[:-1]) & ~pd.isna(values[1:]) & ~pd.isna(values[:-1])
            )
    boundaries = np.append(np.flatnonzero(~connected), len(bars))
    next_boundary = boundaries[np.searchsorted(boundaries, indices, side="right")]
    return np.minimum(MAX_HORIZON, next_boundary - indices - 1)


def payoff_matrix(
    bars: pd.DataFrame,
    indices: Iterable[int],
    atr_values: Iterable[float],
    actions: Iterable[Action] = action_grid(),
    cost: float = 1.0,
) -> np.ndarray:
    """Return net action payoffs as float32[n opportunities, n actions].

    Censored outcomes are NaN. For the full grid there are only 24 first-hit
    scans, one per direction/TP/SL combination; each scan supplies all 45 caps.
    Computation uses O(n opportunities) temporary memory beyond the output.
    Callers select a common 45-observed-bar cohort when fitting payoff tables.
    """
    indices, atr_values, cost = _matrix_inputs(bars, indices, atr_values, cost)
    actions = tuple(actions)
    if any(not isinstance(action, Action) for action in actions):
        raise TypeError("actions must contain only Action instances")
    output = np.full((len(indices), len(actions)), np.nan, dtype=np.float32)
    if not len(indices) or not actions:
        return output
    prices = [bars[column].to_numpy(dtype=np.float64, copy=False) for column in _PRICE_COLUMNS]
    open_, high, low, close = prices
    available = _available_bars(bars, indices, prices)
    entry_rows = np.minimum(indices + 1, len(bars) - 1)
    entry = open_[entry_rows]
    groups: dict[tuple[int, float, float], dict[int, list[int]]] = {}
    for column, action in enumerate(actions):
        group = groups.setdefault((action.direction, action.tp_atr, action.sl_atr), {})
        group.setdefault(action.horizon, []).append(column)

    for (direction, tp_atr, sl_atr), horizons in groups.items():
        with np.errstate(over="ignore"):
            tp = np.maximum(1, np.floor(atr_values * tp_atr / TICK_SIZE + 0.5)) * TICK_SIZE
            sl = np.maximum(1, np.floor(atr_values * sl_atr / TICK_SIZE + 0.5)) * TICK_SIZE
        if not np.all(np.isfinite(tp) & np.isfinite(sl)):
            raise ValueError("distance is too large")
        target = entry + direction * tp
        stop = entry - direction * sl
        alive = available >= 1
        resolved = np.zeros(len(indices), dtype=bool)
        gross = np.full(len(indices), np.nan)
        for offset in range(1, max(horizons) + 1):
            rows = np.minimum(indices + offset, len(bars) - 1)
            alive &= available >= offset
            current_open, current_high, current_low = open_[rows], high[rows], low[rows]
            stop_open = alive & (direction * (current_open - stop) <= 0)
            target_open = alive & ~stop_open & (direction * (current_open - target) >= 0)
            remaining = alive & ~stop_open & ~target_open
            if direction == 1:
                stop_touch = remaining & (current_low <= stop)
                target_touch = remaining & ~stop_touch & (current_high >= target)
            else:
                stop_touch = remaining & (current_high >= stop)
                target_touch = remaining & ~stop_touch & (current_low <= target)
            gross[stop_open] = direction * (current_open[stop_open] - entry[stop_open])
            gross[target_open | target_touch] = tp[target_open | target_touch]
            gross[stop_touch] = -sl[stop_touch]
            finished = stop_open | target_open | stop_touch | target_touch
            resolved |= finished
            alive &= ~finished
            if offset in horizons:
                values = np.where(
                    resolved,
                    gross - cost,
                    np.where(alive, direction * (close[rows] - entry) - cost, np.nan),
                )
                for column in horizons[offset]:
                    output[:, column] = values
    return output
