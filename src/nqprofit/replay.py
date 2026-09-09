"""Causal decision eligibility and a single-position historical policy replay."""

import numpy as np
import pandas as pd

from .execution import Action, simulate_trade
from .policies import select_action

MINUTE = pd.Timedelta(minutes=1)
MINUTE_NS = 60_000_000_000


def decision_indices(bars, features):
    """The UTC clock is applied to the completed close, never future rows."""
    close_times = pd.DatetimeIndex(bars.timestamp) + MINUTE
    valid = features.valid.to_numpy(bool)
    if "atr14" in features:
        valid = valid & (features.atr14.to_numpy() > 0)
    return np.flatnonzero(valid & (close_times.minute % 5 == 0))


def complete_future(bars, indices, horizon=45):
    """Fit-only common completeness; never use this to filter replay decisions."""
    if not isinstance(horizon, int) or not 1 <= horizon <= 45:
        raise ValueError("rejected — out of scope: horizon must be 1..45")
    indices = np.asarray(indices, dtype=int)
    if ((indices < 0) | (indices >= len(bars))).any():
        raise ValueError("indices outside bars")
    if bars.empty:
        return np.array([], dtype=bool)
    times = pd.DatetimeIndex(bars.timestamp).as_unit("ns").asi8
    breaks = np.r_[True, np.diff(times) != MINUTE_NS]
    for column in ("contract", "segment_id"):
        if column in bars:
            values = bars[column].astype("string").fillna("<missing>").to_numpy()
            breaks[1:] |= values[1:] != values[:-1]
    ends = np.r_[np.flatnonzero(breaks)[1:] - 1, len(bars) - 1]
    segment = np.cumsum(breaks) - 1
    return ends[segment[indices]] - indices >= horizon


def feasible_horizons(bars, schedule, period_end):
    """Known calendar spans and study endpoint only; no observation-gap peeking."""
    period_end = pd.Timestamp(period_end)
    if period_end.tzinfo is None:
        raise ValueError("period_end must be timezone aware")
    spans = []
    for row in schedule.itertuples(index=False):
        start, end = row.market_open, min(row.market_close, period_end)
        break_start = getattr(row, "break_start", pd.NaT)
        break_end = getattr(row, "break_end", pd.NaT)
        if pd.notna(break_start) and pd.notna(break_end):
            spans.extend([(start, min(break_start, end)), (break_end, end)])
        else:
            spans.append((start, end))
    spans = sorted((a, b) for a, b in spans if a < b)
    result = np.zeros(len(bars), dtype=np.int16)
    if not spans or bars.empty:
        return result
    starts = np.array([a.value for a, _ in spans], dtype=np.int64)
    ends = np.array([b.value for _, b in spans], dtype=np.int64)
    if (starts[1:] < ends[:-1]).any():
        raise ValueError("calendar spans overlap")
    entries = pd.DatetimeIndex(bars.timestamp).as_unit("ns").asi8 + MINUTE_NS
    positions = np.searchsorted(starts, entries, side="right") - 1
    safe = np.maximum(positions, 0)
    inside = (positions >= 0) & (entries < ends[safe])
    result[inside] = np.minimum(45, (ends[safe[inside]] - entries[inside]) // MINUTE_NS)
    return result


def replay_policy(bars, features, indices, horizons, states, model, cost=1.0):
    """Evaluate choices using only the frozen table and information at detection.

    Observed outcomes determine occupancy, not whether an attempt enters the log.
    Censored attempts remain logged and block the entire qualification gate.
    """
    result = {
        "policy_id": model["policy_id"],
        "decisions": len(indices),
        "occupied_decisions": 0,
        "abstained_decisions": 0,
        "trades": [],
    }
    busy_until = None
    choices = {}
    for index in indices:
        index = int(index)
        decision = pd.Timestamp(bars.timestamp.iloc[index]) + MINUTE
        if busy_until is not None and decision < busy_until:
            result["occupied_decisions"] += 1
            continue
        key = (int(states[index]), int(horizons[index]))
        if key not in choices:
            choices[key] = select_action(model, *key)
        action = choices[key]
        if action is None:
            result["abstained_decisions"] += 1
            continue
        specification = Action(
            action["direction"], action["tp_atr"], action["sl_atr"], action["horizon"]
        )
        trade = simulate_trade(
            bars, index, specification, float(features.atr14.iloc[index]), cost=cost
        )
        trade.update(
            policy_id=model["policy_id"],
            state=int(states[index]),
            predicted_net_points=action["predicted_net_points"],
            ranking_score=action["ranking_score"],
        )
        result["trades"].append(trade)
        busy_until = pd.Timestamp(trade["exit_time"])
    result["attempted_trades"] = len(result["trades"])
    return result
