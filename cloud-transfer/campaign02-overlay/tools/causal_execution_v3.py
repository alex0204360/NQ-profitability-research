"""Causal v3 replay with a horizon frozen at signal time."""
import math

import numpy as np
import pandas as pd

from tools.mnq_oracle_execution import summarize

INSTRUMENTS = {"MNQ": {"point_value": 2., "tick_size": .25}, "NQ": {"point_value": 20., "tick_size": .25}}

def instrument_config(instrument, costs):
    if set(costs) != {"commission_per_side", "slippage_ticks_per_side"}:
        raise ValueError("Only commission and slippage cost keys are allowed")
    if instrument not in INSTRUMENTS:
        raise ValueError("Unknown instrument")
    for key in ("commission_per_side", "slippage_ticks_per_side"):
        value = costs.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("Invalid cost configuration")
    if costs["slippage_ticks_per_side"] != int(costs["slippage_ticks_per_side"]):
        raise ValueError("Slippage must be whole ticks")
    return {"instrument": instrument, **INSTRUMENTS[instrument], **costs}

def annotate(metrics, config, feed_instrument):
    metrics["execution_version"] = "causal-v2"
    metrics["volume_eligibility"] = "previous_completed_candle"
    metrics["instrument"] = config["instrument"]
    metrics["feed_instrument"] = feed_instrument
    metrics["hypothetical_cross_instrument"] = config["instrument"] != feed_instrument
    metrics["execution_assumptions"] = config
    return metrics

def replay_causal(bars, signals, atr, start, end, rule, costs, instrument="MNQ", feed_instrument="MNQ", exit_policy=None, on_state=None, holding_bars=None):
    config = instrument_config(instrument, costs)
    point_value, tick_size = config["point_value"], config["tick_size"]
    if rule not in ("time10", "atr1_target1.5_time30"):
        raise ValueError("Unknown exit rule")
    if len(signals) != len(bars) or len(atr) != len(bars) or not np.isin(signals, [-1, 0, 1]).all():
        raise ValueError("Invalid signal or ATR arrays")
    if holding_bars is None:
        holding_bars = np.full(len(bars), 10 if rule == "time10" else 30, dtype=int)
    holding_bars = np.asarray(holding_bars)
    allowed_horizons = [3, 5, 10, 20] if rule == "time10" else [30]
    if (holding_bars.shape != (len(bars),) or holding_bars.dtype.kind not in "iu"
            or not np.isin(holding_bars[signals != 0], allowed_horizons).all()):
        raise ValueError("Signal-time holding horizon must be 3, 5, 10 or 20 bars")
    if not bars.timestamp.is_monotonic_increasing or bars.timestamp.duplicated().any():
        raise ValueError("Bars must have increasing unique timestamps")
    if not np.isfinite(bars[["open", "high", "low", "close", "volume"]].to_numpy(float)).all():
        raise ValueError("Nonfinite candle")
    if feed_instrument not in INSTRUMENTS:
        raise ValueError("Unknown feed instrument")
    queued_exit = False
    timestamps = pd.DatetimeIndex(bars.timestamp)
    positions = np.flatnonzero((timestamps >= pd.Timestamp(start)) & (timestamps < pd.Timestamp(end)))
    fills, events, equity = [], [], []
    position = None
    realized = peak = drawdown = 0.
    slip = tick_size * costs["slippage_ticks_per_side"]
    fees = 2 * costs["commission_per_side"]
    if not len(positions):
        metrics = annotate(summarize(fills, events, equity, drawdown), config, feed_instrument)
        metrics["execution_version"] = "causal-v3-selected-horizon"
        return metrics, fills, events
    prices = bars[["open", "high", "low", "close", "volume"]].to_numpy(float)
    final_index = positions[-1]
    previous_index = None
    for index in positions:
        open_price, high, low, close, _volume = prices[index]
        contiguous = previous_index is not None and timestamps[index] - timestamps[previous_index] == pd.Timedelta(minutes=1)
        exit_reason = None
        exit_raw = None
        if position is not None and not contiguous:
            exit_reason, exit_raw = "unresolved_gap_next_observed_open", open_price
            events.append({"index": int(index), "kind": exit_reason, "entry_index": position["entry_index"], "missing_minutes": int((timestamps[index] - timestamps[previous_index]).total_seconds()/60)-1})
        if position is None and contiguous and signals[previous_index] != 0:
            side = int(signals[previous_index])
            if prices[previous_index, 4] <= 0 or not np.isfinite(atr[previous_index]):
                events.append({"index": int(index), "kind": "entry_cancelled_no_volume_or_atr"})
            else:
                entry = open_price + side * slip
                stop_distance = max(1., np.floor(float(atr[previous_index]) / tick_size + .5) * tick_size)
                target_distance = max(1., np.floor(float(atr[previous_index]) * 1.5 / tick_size + .5) * tick_size)
                position = {"side": side, "entry_index": int(index), "signal_index": int(previous_index), "entry": entry, "entry_raw": open_price, "stop": entry-side*stop_distance, "target": entry+side*target_distance, "planned_horizon": int(holding_bars[previous_index])}
        elif position is None and previous_index is not None and not contiguous and signals[previous_index] != 0:
            events.append({"index": int(index), "kind": "signal_cancelled_gap"})
        if position is not None:
            side = position["side"]
            held = int(index-position["entry_index"]+1)
            if exit_reason is None and queued_exit:
                exit_raw, exit_reason = open_price, "student_exit_next_open"
                queued_exit = False
            if exit_reason is None and rule != "time10":
                stop, target = position["stop"], position["target"]
                stop_hit = low <= stop if side == 1 else high >= stop
                target_hit = high >= target if side == 1 else low <= target
                if stop_hit:
                    exit_raw = min(open_price, stop) if side == 1 else max(open_price, stop)
                    exit_reason = "stop_first_ambiguous" if target_hit else "stop"
                elif target_hit:
                    exit_raw, exit_reason = target, "target"
            if exit_reason is None and held >= (position["planned_horizon"] if rule == "time10" else 30):
                exit_raw, exit_reason = close, "time_limit"
            if exit_reason is None and index == final_index:
                exit_raw, exit_reason = close, "evaluation_end"
            if exit_reason is not None:
                exit_price = exit_raw-side*slip
                gross = side*(exit_raw-position["entry_raw"])*point_value
                slippage = slip*2*point_value
                net = side*(exit_price-position["entry"])*point_value-fees
                realized += net
                fills.append({**position, "signal_time": timestamps[position["signal_index"]].isoformat(), "entry_time": timestamps[position["entry_index"]].isoformat(), "exit_bar_time": timestamps[index].isoformat(), "exit_time": (timestamps[index]+pd.Timedelta(minutes=1) if exit_reason in ("time_limit", "evaluation_end") else timestamps[index]).isoformat(), "exit_time_precision": "bar_close" if exit_reason in ("time_limit", "evaluation_end") else "bar_open" if exit_reason in ("student_exit_next_open", "unresolved_gap_next_observed_open") else "intrabar_unknown", "exit_index": int(index), "exit": exit_price, "exit_raw": exit_raw, "held_bars": held, "gross_price_move": gross, "commissions": fees, "slippage": slippage, "net": net, "reason": exit_reason})
                position = None
                queued_exit = False
        liquidatable = realized if position is None else realized + position["side"]*(close-position["entry"])*point_value-slip*point_value-fees
        if position is not None:
            side = position["side"]
            context = {**position, "index": int(index), "time": timestamps[index].isoformat(),
                       "available_at": (timestamps[index]+pd.Timedelta(minutes=1)).isoformat(),
                       "held_bars": int(index-position["entry_index"]+1), "price": float(close),
                       "unrealized_points": float(side*(close-position["entry"])),
                       "distance_to_stop_points": float(side*(close-position["stop"])),
                       "distance_to_target_points": float(side*(position["target"]-close)),
                       "realized_net": realized, "liquidatable_equity": liquidatable}
            queued_exit = bool(exit_policy(context)) if exit_policy is not None else False
            context["decision"] = "exit_queued" if queued_exit else "hold"
            if on_state is not None:
                on_state(dict(context))
        peak = max(peak, liquidatable)
        drawdown = max(drawdown, peak-liquidatable)
        equity.append({"timestamp": (timestamps[index]+pd.Timedelta(minutes=1)).isoformat(), "equity": liquidatable})
        previous_index = index
    metrics = annotate(summarize(fills, events, equity, drawdown), config, feed_instrument)
    metrics["execution_version"] = "causal-v3-selected-horizon"
    return metrics, fills, events
