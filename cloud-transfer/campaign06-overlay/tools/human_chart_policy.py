"""Causal, inspectable MNQ chart setups and training-only probability gate."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import beta

SETUPS = ("horizontal", "trendline")
SIDES = (1, -1)


def confirmed_trendlines(bars: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Project lines through the last two pivots, each known two bars later."""
    n = len(bars)
    support = np.full(n, np.nan)
    resistance = np.full(n, np.nan)
    support_slope = np.full(n, np.nan)
    resistance_slope = np.full(n, np.nan)
    lows, highs = bars.low.to_numpy(float), bars.high.to_numpy(float)
    segments = bars.segment.to_numpy()
    last_segment = None
    low_pivots: list[tuple[int, float]] = []
    high_pivots: list[tuple[int, float]] = []
    for i in range(n):
        if segments[i] != last_segment:
            low_pivots, high_pivots = [], []
            last_segment = segments[i]
        p = i - 2
        if p >= 2 and segments[p - 2] == segments[i]:
            if all(lows[p] < lows[j] for j in (p-2, p-1, p+1, p+2)):
                low_pivots.append((p, lows[p]))
                low_pivots = low_pivots[-2:]
            if all(highs[p] > highs[j] for j in (p-2, p-1, p+1, p+2)):
                high_pivots.append((p, highs[p]))
                high_pivots = high_pivots[-2:]
        for pivots, projection, slope_out in ((low_pivots, support, support_slope),
                                               (high_pivots, resistance, resistance_slope)):
            if len(pivots) == 2:
                (first_index, first_price), (second_index, second_price) = pivots
                if 5 <= second_index - first_index <= 90 and i - second_index <= 90:
                    slope = (second_price - first_price) / (second_index - first_index)
                    projection[i] = second_price + slope * (i - second_index)
                    slope_out[i] = slope
    return support, resistance, support_slope, resistance_slope


def chart_setups(bars: pd.DataFrame, states: pd.DataFrame, ready: np.ndarray) -> tuple[np.ndarray, dict]:
    """Return raw horizontal/trendline signals, without looking past each bar."""
    n = len(bars)
    if len(states) != n or ready.shape != (n,):
        raise ValueError("Aligned bars, state, and readiness required")
    atr = states.atr14.to_numpy(float)
    close, open_, low, high = (bars[col].to_numpy(float) for col in ("close", "open", "low", "high"))
    trend = states.ema_spread_atr.to_numpy(float)
    strength = states.trend_strength.to_numpy(float)
    support = close - states.support_distance_atr.to_numpy(float) * atr
    resistance = close + states.resistance_distance_atr.to_numpy(float) * atr
    confirmed_support = states.support_confirmed.to_numpy(bool) & ~states.support_missing.to_numpy(bool)
    confirmed_resistance = states.resistance_confirmed.to_numpy(bool) & ~states.resistance_missing.to_numpy(bool)
    dist_support = states.support_distance_atr.to_numpy(float)
    dist_resistance = states.resistance_distance_atr.to_numpy(float)
    common = ready & np.isfinite(atr) & (atr > 0) & (strength >= .12)
    horizontal_long = (common & (trend > 0) & confirmed_support &
                       (np.abs(low - support) <= .25 * atr) & (close >= support + .10 * atr) &
                       (close > open_) & (dist_resistance >= .75))
    horizontal_short = (common & (trend < 0) & confirmed_resistance &
                        (np.abs(high - resistance) <= .25 * atr) & (close <= resistance - .10 * atr) &
                        (close < open_) & (dist_support >= .75))
    trend_support, trend_resistance, slope_support, slope_resistance = confirmed_trendlines(bars)
    trendline_long = (common & (trend > 0) & (10 * slope_support / atr >= .05) &
                      (10 * slope_support / atr <= 1.) &
                      (np.abs(low - trend_support) <= .25 * atr) &
                      (close >= trend_support + .10 * atr) & (close <= trend_support + .75 * atr) &
                      (close > open_))
    trendline_short = (common & (trend < 0) & (10 * -slope_resistance / atr >= .05) &
                       (10 * -slope_resistance / atr <= 1.) &
                       (np.abs(high - trend_resistance) <= .25 * atr) &
                       (close <= trend_resistance - .10 * atr) & (close >= trend_resistance - .75 * atr) &
                       (close < open_))
    setups = np.zeros((n, 2, 2), dtype=bool)  # setup, direction: long/short
    setups[:, 0, 0], setups[:, 0, 1] = horizontal_long, horizontal_short
    setups[:, 1, 0], setups[:, 1, 1] = trendline_long, trendline_short
    return setups, {"horizontal_support": np.where(confirmed_support, support, np.nan),
                    "horizontal_resistance": np.where(confirmed_resistance, resistance, np.nan),
                    "trendline_support": trend_support, "trendline_resistance": trend_resistance}


def calibrate(setups: np.ndarray, robust_net: np.ndarray, valid: np.ndarray,
              training: np.ndarray) -> dict:
    if (setups.ndim != 3 or setups.shape[1:] != (2, 2) or robust_net.shape != (len(setups), 2)
            or valid.shape != (len(setups),) or training.shape != (len(setups),)):
        raise ValueError("Aligned two-setup, two-side training arrays required")
    output = {}
    for j, setup in enumerate(SETUPS):
        for k, side in enumerate(SIDES):
            mask = setups[:, j, k] & valid & training
            values = robust_net[mask, k]
            wins = values[values > 0]
            losses = -values[values <= 0]
            n = len(values)
            posterior = (len(wins) + 2) / (n + 4)
            lower = float(beta.ppf(.10, len(wins) + 2, len(losses) + 2))
            mean_gain = float(wins.mean()) if len(wins) else None
            mean_loss = float(losses.mean()) if len(losses) else None
            breakeven = (mean_loss / (mean_gain + mean_loss)) if mean_gain is not None and mean_loss is not None else None
            mean_net = float(values.mean()) if n else None
            allowed = bool(n >= 20 and breakeven is not None and lower > breakeven and mean_net > 0)
            output[f"{setup}_{'long' if side == 1 else 'short'}"] = {
                "examples": n, "wins": len(wins), "losses": len(losses),
                "posterior_win_probability": posterior, "lower_10pct_win_probability": lower,
                "empirical_breakeven_probability": breakeven,
                "mean_robust_stress_net_usd": mean_net, "allowed": allowed}
    return output


def signals(setups: np.ndarray, calibration: dict, gated: bool) -> tuple[np.ndarray, list[str]]:
    n = len(setups)
    signal = np.zeros(n, dtype=int)
    reasons = ["no_completed_chart_setup"] * n
    for i in range(n):
        active = []
        for j, setup in enumerate(SETUPS):
            for k, side in enumerate(SIDES):
                if not setups[i, j, k]:
                    continue
                key = f"{setup}_{'long' if side == 1 else 'short'}"
                row = calibration[key]
                if not gated or row["allowed"]:
                    active.append((setup, side, row["mean_robust_stress_net_usd"] or 0.))
        if not active:
            if setups[i].any():
                reasons[i] = "setup_failed_probability_gate" if gated else "setup_conflict"
            continue
        if len({side for _, side, _ in active}) > 1:
            reasons[i] = "conflicting_chart_directions"
            continue
        chosen = max(active, key=lambda row: (row[2], row[0] == "horizontal"))
        signal[i] = chosen[1]
        reasons[i] = f"{chosen[0]}_{'long' if chosen[1] == 1 else 'short'}_retest"
    return signal, reasons
