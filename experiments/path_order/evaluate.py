"""Score frozen circuits. All return labels and trade diagnostics live here."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from brain import activations
from data import discovery, regular_hours
from execution import replay

HORIZONS = [1, 8, 24]


def describe(trades, marks, calendar):
    pnl = trades.net_usd.astype(float)
    equity = np.r_[0., marks.to_numpy()]
    days = marks.groupby(marks.index.date).last().reindex(calendar)
    days = days.diff().fillna(days.iloc[0])
    durations = (trades.exit_time - trades.entry_time).dt.total_seconds() / 60 if len(trades) else []
    return dict(trades=len(pnl), net=float(pnl.sum()), gross=float(trades.gross_usd.sum()),
                expectancy=float(pnl.mean()) if len(pnl) else None,
                median_net=float(pnl.median()) if len(pnl) else None,
                drawdown=float((np.maximum.accumulate(equity) - equity).max()),
                net_without_best_day=float(pnl.sum() - days.max()),
                net_without_gap_trades=float(pnl[trades.reason != "gap"].sum()),
                gap_trades=int((trades.reason == "gap").sum()),
                median_minutes=float(np.median(durations)) if len(pnl) else None,
                active_days=int(trades.entry_time.map(lambda t: t.date()).nunique()),
                by_side={k: {"trades": len(v), "net": float(v.net_usd.sum())}
                         for k, v in trades.groupby("side")}), days


def paired(a, b):
    delta = np.asarray(a - b)
    n = len(delta)
    starts = np.random.default_rng(2101).integers(n, size=(5000, (n + 4) // 5))
    indices = ((starts[:, :, None] + np.arange(5)) % n).reshape(5000, -1)[:, :n]
    # A five-day panel contains just one full block; suppress meaningless intervals.
    interval = np.quantile(delta[indices].mean(axis=1), [.025, .975]).tolist() if n >= 10 else None
    return {"mean_usd_per_day": float(delta.mean()), "block95": interval}


def forward_labels(bars, a, model):
    """Contiguous, next-open reference returns; labels are never passed to replay."""
    result = {}
    t = bars.index.to_series()
    for h in HORIZONS:
        valid = t.shift(-1-h) - t == pd.Timedelta(minutes=h+1)
        change = (bars.open.shift(-1-h) - bars.open.shift(-1)).where(valid)
        sample = pd.DataFrame({"move": change, "score": a[model], "trend": a.trend,
                               "effort_first": a.effort_first, "motion_first": a.motion_first})
        sample = sample.loc[sample.score.abs() > 1.5].dropna()
        aligned = sample.move * np.sign(sample.score)
        groups = {"all": np.ones(len(sample), bool),
                  "effort_first_dominant": sample.effort_first.abs() >= sample.motion_first.abs(),
                  "motion_first_dominant": sample.effort_first.abs() < sample.motion_first.abs(),
                  "agrees_with_trend": sample.score * sample.trend > 0,
                  "opposes_trend": sample.score * sample.trend < 0}
        if "stock" in a.columns:
            # These groups describe reservoir activations; ordering-branch diagnostics
            # belong only to the original network.
            groups = {k: v for k, v in groups.items() if "dominant" not in k}
        result[h] = {key: {"n": int(mask.sum()), "mean_signed_points": float(aligned[mask].mean())
                           if mask.sum() else None} for key, mask in groups.items()}
    return result


def evaluate(bars, models, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    calendar = np.unique(bars.index.date)
    shared = activations(bars)
    signals = {k: shared[k] for k in ["area", "symmetric", "trend"]}
    signals["cash"] = pd.Series(0., index=bars.index)
    states = {"area": shared}
    for model in models:
        if model != "area":
            states[model] = activations(bars, model)
            signals[model] = states[model][model]
    results = {"bars": len(bars), "dates": [str(d) for d in calendar],
               "off_tick_ohlc_rows": int(((bars.iloc[:, :4] * 4) % 1 != 0).any(axis=1).sum()),
               "zero_volume_bars": int((bars.volume == 0).sum()),
               "forward": {m: forward_labels(bars, a, m) for m, a in states.items()},
               "replays": {}}
    for delay in [0, 1]:
        for cost in [3., 6.]:
            scenario = f"delay{delay}_cost{int(cost)}"
            summaries, daily = {}, {}
            for name, signal in signals.items():
                trades, marks = replay(bars, signal, delay=delay, cost=cost)
                summaries[name], daily[name] = describe(trades, marks, calendar)
                if name in states and len(trades):
                    a = states[name].reindex(trades.signal_time)
                    a.index = trades.index
                    sign = np.sign(a.trend)
                    matched = (trades.exit - trades.entry) * sign * 2 - cost * sign.abs()
                    summaries[name]["matched_trend_net"] = float(matched.sum())
                    paired_trades = trades.net_usd - matched
                    matched_days = paired_trades.groupby(trades.exit_time.dt.date).sum().reindex(calendar, fill_value=0)
                    summaries[name]["direction_delta_vs_matched"] = paired(matched_days, 0.)
                    if cost == 3:
                        internal = (["charge", "stock", "signed_release"] if "stock" in a
                                    else ["effort_first", "motion_first"])
                        fields = [name, "scale", "effort", "motion", *internal, "trend"]
                        output = pd.concat([trades, a[fields], matched.rename("matched_trend_net")], axis=1)
                        output.to_csv(directory / f"{name}-delay{delay}.csv", index=False, float_format="%.9g")
            for name in states:
                summaries[name]["daily_delta"] = {k: paired(daily[name], daily[k])
                    for k in ["cash", "symmetric", "trend", "area", "volume_control"] if k in daily and k != name}
            pd.DataFrame(daily).to_csv(directory / f"{scenario}-daily.csv", index_label="et_date")
            results["replays"][scenario] = summaries
    (directory / "results.json").write_text(json.dumps(results, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--discovery", type=Path)
    src.add_argument("--november", type=Path, help="frozen private CSV from capture.py")
    src.add_argument("--extension", type=Path, nargs=2, help="two registered private extension CSVs in time order")
    p.add_argument("--models", nargs="+", default=["area"])
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    if args.discovery:
        bars = discovery(args.discovery)
    elif args.extension:
        bounds = [("2026-11-03", "2026-11-06"), ("2026-11-09", "2026-11-13")]
        bars = pd.concat([regular_hours(pd.read_csv(path), *dates)
                          for path, dates in zip(args.extension, bounds, strict=True)])
    else:
        bars = regular_hours(pd.read_csv(args.november), "2026-11-16", "2026-11-20")
    evaluate(bars, args.models, args.out)
