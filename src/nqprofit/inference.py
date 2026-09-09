"""Descriptive trade accounting and paired, dependent-day profit evidence.

Daily P&L is booked to ET entry-date cohorts, not marked to market. The block
bootstrap keeps policy payoffs, counts, and benchmark payoffs paired on the full
calendar, and never moves a block across a walk-forward period boundary. The
caller owns screening and the once-only held-out evaluation protocol.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from numbers import Integral
from typing import Any

import numpy as np
import pandas as pd

ET = "America/New_York"
EXIT_REASONS = ("tp", "sl", "timeout", "censored")
Z95 = 1.959963984540054


def _aware_timestamp(value: Any, name: str) -> pd.Timestamp:
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {name}") from exc
    if pd.isna(stamp) or stamp.tzinfo is None:
        raise ValueError(f"{name} must be a finite timezone-aware timestamp")
    return stamp


def _checked_trades(trades: list[dict]) -> list[dict]:
    checked = []
    for source in trades:
        entry = _aware_timestamp(source.get("entry_time"), "entry_time")
        reason = source.get("exit_reason")
        if reason not in EXIT_REASONS:
            raise ValueError(f"Invalid exit reason: {reason}")
        item = dict(source, _entry=entry)
        if reason != "censored":
            exit_time = _aware_timestamp(source.get("exit_time"), "exit_time")
            elapsed = (exit_time - entry).total_seconds()
            if elapsed < 0 or elapsed > 45 * 60:
                raise ValueError("Priced exit must be within 45 elapsed minutes of entry")
            bars = source.get("resolution_bars")
            if isinstance(bars, bool) or not isinstance(bars, Integral) or not 1 <= bars <= 45:
                raise ValueError("resolution_bars must be an integer from 1 to 45")
            for key in ("gross_points", "net_points"):
                try:
                    value = float(source[key])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(f"Missing or invalid {key}") from exc
                if not np.isfinite(value):
                    raise ValueError(f"{key} must be finite")
                item[key] = value
            item["resolution_bars"] = int(bars)
            item["_exit"] = exit_time
        checked.append(item)
    return checked


def _wilson(successes: int, n: int) -> list[float] | None:
    if not n:
        return None
    p = successes / n
    denom = 1 + Z95**2 / n
    center = (p + Z95**2 / (2 * n)) / denom
    half = Z95 * np.sqrt(p * (1 - p) / n + Z95**2 / (4 * n**2)) / denom
    return [max(0.0, float(center - half)), min(1.0, float(center + half))]


def _resolution(records: list[dict]) -> dict:
    values = np.asarray([r["resolution_bars"] for r in records], dtype=float)
    result: dict[str, Any] = {"n": len(values)}
    result["mean"] = float(values.mean()) if len(values) else None
    for name, quantile in (
        ("p10", 0.1),
        ("p25", 0.25),
        ("median", 0.5),
        ("p75", 0.75),
        ("p90", 0.9),
    ):
        result[name] = float(np.quantile(values, quantile)) if len(values) else None
    result["max"] = int(values.max()) if len(values) else None
    result["histogram"] = {str(k): v for k, v in sorted(Counter(int(v) for v in values).items())}
    return result


def _payoff_stats(net: np.ndarray) -> dict:
    n = len(net)
    profits = float(net[net > 0].sum())
    losses = -float(net[net < 0].sum())
    equity = np.r_[0.0, np.cumsum(net)]
    return {
        "total_points": float(net.sum()),
        "mean_points": float(net.mean()) if n else None,
        "positive_net_rate": float(np.mean(net > 0)) if n else None,
        "profit_factor": profits / losses if losses > 0 else None,
        "loss_free": bool(n and losses == 0),
        "max_drawdown_points": float(np.max(np.maximum.accumulate(equity) - equity)),
    }


def _breakdown(records: list[dict], key: str) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[str(record.get(key, "unknown"))].append(record)
    result = {}
    for label in sorted(groups):
        members = groups[label]
        net = np.asarray([r["net_points"] for r in members])
        successes = int(np.count_nonzero(net > 0))
        result[label] = {
            "n": len(members),
            "low_confidence": len(members) < 30,
            "mean_net_points": float(net.mean()),
            "total_net_points": float(net.sum()),
            "hit_rate": successes / len(members),
            "hit_rate_ci95": _wilson(successes, len(members)),
            "tp_rate": sum(r["exit_reason"] == "tp" for r in members) / len(members),
            "resolution": _resolution(members),
        }
    return result


def summarize_trades(trades: list[dict]) -> dict:
    """Return JSON-safe descriptive statistics, excluding censored payoffs.

    P&L stored on each priced trade defines primary summary results. Cost
    scenarios separately subtract the preregistered friction from gross points.
    Undefined ratios (including loss-free profit factors) are ``None``, never
    nonstandard JSON Infinity. Wilson intervals describe trade proportions and
    are not significance evidence under serial dependence.
    """
    checked = _checked_trades(trades)
    priced = sorted(
        (r for r in checked if r["exit_reason"] != "censored"),
        key=lambda r: (r["_exit"], r["_entry"]),
    )
    n = len(priced)
    gross = np.asarray([r["gross_points"] for r in priced], dtype=float)
    net = np.asarray([r["net_points"] for r in priced], dtype=float)
    primary = _payoff_stats(net)
    exit_counts = {
        reason: sum(r["exit_reason"] == reason for r in checked) for reason in EXIT_REASONS
    }
    dates = {r["_entry"].tz_convert(ET).date().isoformat() for r in priced}
    weeks = {tuple(r["_entry"].tz_convert(ET).isocalendar()[:2]) for r in priced}
    scenarios = {}
    for name, cost, point_value in (
        ("nq_primary", 1.0, 20.0),
        ("nq_stress", 2.0, 20.0),
        ("mnq_proxy_primary", 1.5, 2.0),
        ("mnq_proxy_stress", 2.5, 2.0),
    ):
        stats = _payoff_stats(gross - cost)
        stats.update(
            round_trip_cost_points=cost,
            point_value_dollars=point_value,
            total_dollars=stats["total_points"] * point_value,
            mean_dollars=stats["mean_points"] * point_value if n else None,
            max_drawdown_dollars=stats["max_drawdown_points"] * point_value,
        )
        scenarios[name] = stats
    return {
        "n": n,
        "priced_trades": n,
        "attempted_trades": len(checked),
        "censored_trades": exit_counts["censored"],
        "coverage": n / len(checked) if checked else None,
        "dates": len(dates),
        "weeks": len(weeks),
        "exit_counts": exit_counts,
        "ambiguous_trades": sum(bool(r.get("ambiguous", False)) for r in priced),
        "hit_rate": primary["positive_net_rate"],
        "hit_rate_ci95": _wilson(int(np.count_nonzero(net > 0)), n),
        "hit_rate_interval_interpretation": "descriptive Wilson, not dependent-trade inference",
        "tp_rate": exit_counts["tp"] / n if n else None,
        "mean_net_points": primary["mean_points"],
        "total_net_points": primary["total_points"],
        "total_gross_points": float(gross.sum()),
        "profit_factor": primary["profit_factor"],
        "loss_free": primary["loss_free"],
        "max_drawdown_points": primary["max_drawdown_points"],
        "cost_scenarios": scenarios,
        "resolution": {
            "overall": _resolution(priced),
            **{
                reason: _resolution([r for r in priced if r["exit_reason"] == reason])
                for reason in EXIT_REASONS
                if reason != "censored"
            },
        },
        "state_breakdown": _breakdown(priced, "state"),
        "action_breakdown": _breakdown(priced, "action_id"),
        "breakdown_interpretation": "descriptive diagnostics; qualification is policy-level",
    }


def _date_boundary(value: Any) -> pd.Timestamp:
    try:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp):
            raise ValueError("Invalid period boundary")
        stamp = stamp.tz_localize(ET) if stamp.tzinfo is None else stamp.tz_convert(ET)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid period boundary") from exc
    if stamp != stamp.normalize():
        raise ValueError("Period boundaries must be midnight America/New_York")
    return stamp


def daily_arrays(trades: list[dict], start: Any, end: Any) -> pd.DataFrame:
    """Book complete trade P&L/count to its ET entry day; keep all calendar days.

    A final trade may resolve exactly at the exclusive end boundary. Attribution
    to the entry-day cohort retains that payoff without extending the period.
    Censored attempts have no invented payoff and are counted in trade summaries.
    """
    first, stop = _date_boundary(start), _date_boundary(end)
    if stop <= first:
        raise ValueError("Period end must follow start")
    days = pd.date_range(first, stop, freq="D", inclusive="left").strftime("%Y-%m-%d")
    frame = pd.DataFrame(
        {"day": days, "pnl": np.zeros(len(days)), "count": np.zeros(len(days), dtype=int)}
    )
    offsets = {day: i for i, day in enumerate(days)}
    for trade in _checked_trades(trades):
        entry = trade["_entry"].tz_convert(ET)
        if not first <= entry < stop:
            raise ValueError("Trade entry is outside the daily-array period")
        if trade["exit_reason"] == "censored":
            continue
        if trade["_exit"] > stop:
            raise ValueError("Trade exit exceeds the daily-array period")
        i = offsets[entry.date().isoformat()]
        frame.at[i, "pnl"] += trade["net_points"]
        frame.at[i, "count"] += 1
    return frame


def _check_daily(frame: pd.DataFrame) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    if not {"day", "pnl", "count"}.issubset(frame.columns) or frame.empty:
        raise ValueError("Each daily period needs day, pnl and count on at least one day")
    try:
        days = pd.DatetimeIndex(pd.to_datetime(frame["day"], errors="raise"))
        pnl = frame["pnl"].to_numpy(dtype=float)
        count = frame["count"].to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid daily data") from exc
    if days.tz is not None or days.hasnans or not days.equals(days.normalize()):
        raise ValueError("Daily labels must be timezone-free calendar dates")
    if not days.equals(pd.date_range(days[0], periods=len(days), freq="D")):
        raise ValueError("Daily periods must contain every calendar date, in order")
    if not np.all(np.isfinite(pnl)) or not np.all(np.isfinite(count)):
        raise ValueError("Daily values must be finite")
    if np.any(count < 0) or np.any(count != np.floor(count)):
        raise ValueError("Daily counts must be nonnegative integers")
    if np.any((count == 0) & (pnl != 0)):
        raise ValueError("Daily P&L without a priced trade is unsupported")
    return days, pnl, count


def _period_values(periods: list[tuple[pd.DataFrame, pd.DataFrame]]) -> list[np.ndarray]:
    if not periods:
        raise ValueError("At least one evaluation period is required")
    arrays = []
    previous_end = None
    for policy, benchmark in periods:
        days, pnl, count = _check_daily(policy)
        baseline_days, baseline_pnl, _ = _check_daily(benchmark)
        if not days.equals(baseline_days):
            raise ValueError("Policy and benchmark calendar days must match exactly")
        if previous_end is not None and days[0] <= previous_end:
            raise ValueError("Evaluation periods must be ordered and nonoverlapping")
        previous_end = days[-1]
        arrays.append(np.column_stack((pnl, count, pnl - baseline_pnl)))
    return arrays


def _sample_totals(
    values: list[np.ndarray],
    block_length: int,
    draws: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample noncircular moving blocks using block prefix sums, in small batches.

    Consecutive observations in each block retain dependence. A short final
    block is truncated to preserve each period's original number of dates.
    Prefix sums avoid materializing draws-by-days-by-three arrays.
    """
    output = np.zeros((draws, 3), dtype=float)
    for period in values:
        n = len(period)
        length = min(block_length, n)
        blocks, tail = divmod(n, length)
        n_starts = blocks + bool(tail)
        cumulative = np.vstack((np.zeros(3), np.cumsum(period, axis=0)))
        window_sums = cumulative[length:] - cumulative[:-length]
        for offset in range(0, draws, 256):
            size = min(256, draws - offset)
            starts = rng.integers(0, n - length + 1, size=(size, n_starts))
            totals = window_sums[starts[:, :blocks]].sum(axis=1)
            if tail:
                last = starts[:, -1]
                totals += cumulative[last + tail] - cumulative[last]
            output[offset : offset + size] += totals
    return output


def bootstrap_evidence(
    periods: list[tuple[pd.DataFrame, pd.DataFrame]],
    draws: int,
    seed: int = 20260909,
    block_lengths: tuple[int, ...] = (5, 20),
) -> dict:
    """Return marginal percentile intervals and conservative joint claim p-value.

    For mean/trade, the centered null uses daily residuals ``pnl - mean*count``
    and retains sampled denominators. The paired null centers daily policy minus
    benchmark P&L. Plus-one p-values use the ``>=`` upper tail. Empty-denominator
    resamples use zero in the reported mean interval and always count against
    significance in the null tail; they can never create positive support.
    """
    if isinstance(draws, bool) or not isinstance(draws, Integral) or draws < 1:
        raise ValueError("draws must be a positive integer")
    if isinstance(seed, bool) or not isinstance(seed, Integral) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if (
        not block_lengths
        or any(
            isinstance(length, bool) or not isinstance(length, Integral) or length < 1
            for length in block_lengths
        )
        or len(set(block_lengths)) != len(block_lengths)
    ):
        raise ValueError("block_lengths must be distinct positive integers")
    values = _period_values(periods)
    observed = np.sum([v.sum(axis=0) for v in values], axis=0)
    total_days = sum(len(v) for v in values)
    observed_mean = float(observed[0] / observed[1]) if observed[1] else 0.0
    observed_advantage = float(observed[2] / total_days)
    block_results = []
    for length in block_lengths:
        rng = np.random.default_rng(np.random.SeedSequence([int(seed), int(length)]))
        sampled = _sample_totals(values, int(length), int(draws), rng)
        counts = sampled[:, 1]
        zero = counts == 0
        means = np.divide(sampled[:, 0], counts, out=np.zeros(draws), where=~zero)
        advantages = sampled[:, 2] / total_days
        # Algebraically equivalent to jointly resampling centered daily residuals.
        centered_mean = np.divide(
            sampled[:, 0] - observed_mean * counts,
            counts,
            out=np.zeros(draws),
            where=~zero,
        )
        centered_advantage = advantages - observed_advantage
        p_mean = (1 + np.count_nonzero(zero | (centered_mean >= observed_mean))) / (draws + 1)
        p_advantage = (1 + np.count_nonzero(centered_advantage >= observed_advantage)) / (draws + 1)
        mean_ci = np.quantile(means, [0.025, 0.975]).tolist()
        advantage_ci = np.quantile(advantages, [0.025, 0.975]).tolist()
        block_results.append(
            {
                "block_length": int(length),
                "effective_period_block_lengths": [min(int(length), len(v)) for v in values],
                "mean_net_per_trade_ci95": mean_ci,
                "daily_advantage_ci95": advantage_ci,
                "mean_net_per_trade_p_value": float(p_mean),
                "daily_advantage_p_value": float(p_advantage),
                "zero_count_resamples": int(zero.sum()),
                "lower_bounds_positive": bool(mean_ci[0] > 0 and advantage_ci[0] > 0),
            }
        )
    return {
        "draws": int(draws),
        "seed": int(seed),
        "calendar_days": total_days,
        "period_days": [len(v) for v in values],
        "observed_trades": int(observed[1]),
        "observed_mean_net_per_trade": observed_mean,
        "observed_mean_daily_advantage": observed_advantage,
        "block_results": block_results,
        "p_value": max(
            max(r["mean_net_per_trade_p_value"], r["daily_advantage_p_value"])
            for r in block_results
        ),
        "lower_bounds_positive": all(r["lower_bounds_positive"] for r in block_results),
        "interval_interpretation": "marginal 95% percentile intervals, not simultaneous",
        "daily_booking": "ET entry-date cohort P&L, not mark-to-market",
        "zero_count_policy": "mean estimate zero; null mean tail always non-supporting",
    }


def holm(pvalues: dict[str, float], alpha: float = 0.05) -> dict[str, dict]:
    """Holm adjusted p-values for the entire frozen family, including p=1 failures."""
    if not np.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must lie strictly between zero and one")
    if any(not np.isfinite(p) or p < 0 or p > 1 for p in pvalues.values()):
        raise ValueError("p-values must be finite numbers from zero to one")
    previous = 0.0
    result = {}
    m = len(pvalues)
    for i, (name, pvalue) in enumerate(
        sorted(pvalues.items(), key=lambda item: (item[1], item[0]))
    ):
        adjusted = min(1.0, max(previous, (m - i) * pvalue))
        previous = adjusted
        result[name] = {"adjusted_p": float(adjusted), "passed": bool(adjusted <= alpha)}
    return result
