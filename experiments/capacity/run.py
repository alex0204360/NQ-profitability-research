"""Backtest frozen capacity gates against the original one-MNQ replay."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.hold_work.metrics import (
    COSTS, drawdown_bounds, equity_events, full_effects, normalize_trades, paired_effects,
)
from experiments.hold_work.replay import (
    BACKGROUND_SPAN, COST, ENTRY_THRESHOLD_POINTS, FIELDS, FLATTEN_TIME,
    MINUTE, POINT_VALUE_USD, TRADE_COLUMNS, Order, activations, replay,
    verify_archived, verify_brain, write_outputs,
)
from experiments.hold_work.sources import load_sources

# (fixed entries, entry gate, exit gate). Both signal types use the same
# original directional reservoir condition and execute at observed opens.
MODELS = {
    "original": (False, None, None),
    "fixed_volume_exit": (True, None, "hold"),
    "full_volume_exit": (False, None, "hold"),
    "fixed_price_exit": (True, None, "price"),
    "full_price_exit": (False, None, "price"),
    "fixed_trail": (True, None, "trail"),
    "full_trail": (False, None, "trail"),
    "full_volume_entry": (False, "hold", None),
    "full_price_entry": (False, "price", None),
    "full_volume_joint": (False, "hold", "hold"),
    "full_price_joint": (False, "price", "price"),
}
LEDGER_COLUMNS = [*TRADE_COLUMNS, "trade_id", "exit_signal_time", "entry_scale", "entry_forecast"]


@dataclass
class Position:
    entry_time: pd.Timestamp
    entry: float
    scale: float
    side: int
    signal_time: pd.Timestamp
    entry_forecast: float
    peak: float = 0.


def simulate(bars, encoded, delay, model, fixed=None):
    """Orders made after completion of a bar are immutable until fill or gap."""
    use_fixed, entry_gate, exit_gate = MODELS[model]
    if use_fixed != (fixed is not None):
        raise ValueError("fixed replay requires the matching original entry signals")
    if not bars.index.equals(encoded.index) or len(set(bars.index.date)) != 1:
        raise ValueError("expected aligned bars and scores from a single session")

    lag = (delay + 1) * MINUTE
    gaps = ~bars.index.to_series().diff().eq(MINUTE)
    scales = (bars.high-bars.low).rename("range").groupby(gaps.cumsum().to_numpy()).transform(
        lambda width: width.ewm(span=BACKGROUND_SPAN, adjust=False).mean().shift()
    ).clip(lower=.25).to_numpy()
    gaps = gaps.to_numpy()
    open_, close = (bars[k].to_numpy() for k in ("open", "close"))
    score = encoded.reservoir.to_numpy()
    margins = {k: encoded[k].to_numpy() for k in ("hold_long", "hold_short", "price_long", "price_short")}
    before_cutoff = np.array([(t + lag).time() < FLATTEN_TIME for t in bars.index])
    trades, path, equity = [], [], []
    position = pending = None
    realized_gross = 0.

    def exit_at(i, reason, signal=None):
        nonlocal position, realized_gross
        gross = POINT_VALUE_USD * position.side * (open_[i] - position.entry)
        realized_gross += gross
        trades.append(dict(
            signal_time=position.signal_time, entry_time=position.entry_time, exit_time=bars.index[i],
            side="long" if position.side == 1 else "short", entry=position.entry, exit=open_[i],
            gross_usd=gross, net_usd=gross-COST, reason=reason, trade_id=position.entry_time.isoformat(),
            exit_signal_time=signal, entry_scale=position.scale, entry_forecast=position.entry_forecast,
        ))
        position = None

    for i, ts in enumerate(bars.index):
        if i and gaps[i]:
            pending = None
            if position is not None:
                exit_at(i, "gap")
        if pending is not None and ts == pending.due:
            order, pending = pending, None
            if order.kind == "entry":
                assert position is None and ts.time() < FLATTEN_TIME
                source_i = i - delay - 1
                position = Position(ts, open_[i], scales[i], order.side, order.bar_start, score[source_i])
            else:
                exit_at(i, order.reason, order.bar_start)
        if ts.time() >= FLATTEN_TIME:
            pending = None
            if position is not None:
                exit_at(i, "time")

        if position is not None:
            direction = position.side
            side = "long" if direction == 1 else "short"
            displacement = direction * (close[i] - position.entry)
            position.peak = max(position.peak, displacement)
            eligible = position.peak >= position.scale
            trail = displacement - position.peak + 2 * position.scale if eligible else position.scale
            raw_exit = not np.isfinite(score[i]) or score[i] * direction <= 0
            discretionary = pending is None and before_cutoff[i] and not raw_exit
            if pending is None and before_cutoff[i]:
                if raw_exit:
                    pending = Order("exit", ts + lag, ts, reason="signal")
                elif eligible and exit_gate is not None:
                    margin = trail if exit_gate == "trail" else margins[f"{exit_gate}_{side}"][i]
                    if margin <= 0:
                        pending = Order("exit", ts + lag, ts, reason="hold")
            if model == "original":
                path.append(dict(
                    trade_id=position.entry_time.isoformat(), entry_time=position.entry_time,
                    side=side, direction=direction, entry=position.entry,
                    entry_scale=position.scale, bar_start=ts, eligible=eligible,
                    displacement=displacement, peak=position.peak, trail_score=trail,
                    hold_score=margins[f"hold_{side}"][i], price_score=margins[f"price_{side}"][i],
                    pending_exit=pending is not None, discretionary=discretionary,
                ))
        elif pending is None and before_cutoff[i]:
            direction = 0
            if use_fixed:
                direction = fixed.get(ts, 0)
            elif np.isfinite(score[i]) and abs(score[i]) > ENTRY_THRESHOLD_POINTS:
                side = "long" if score[i] > 0 else "short"
                if entry_gate is None or margins[f"{entry_gate}_{side}"][i] > 0:
                    direction = 1 if side == "long" else -1
            if direction:
                pending = Order("entry", ts + lag, ts, side=direction)

        floating = 0. if position is None else POINT_VALUE_USD * position.side * (close[i] - position.entry)
        equity.append((realized_gross + floating, len(trades), int(position is not None)))

    if position is not None:
        raise ValueError("session ended with an open position")
    trades = pd.DataFrame(trades, columns=LEDGER_COLUMNS)
    equity = pd.DataFrame(equity, index=bars.index, columns=["gross_equity_usd", "completed_trades", "occupancy"])
    trace = pd.DataFrame(path)
    if len(trace):
        events = pd.DataFrame({"next_executable_price": bars.open.shift(-delay-1),
                               "next_executable_time": bars.index.to_series().shift(-delay-1)})
        can_fill = ((events.next_executable_time - bars.index.to_series()).eq(lag)
                    & events.next_executable_time.dt.time.le(FLATTEN_TIME))
        events = events.where(can_fill)
        trace = trace.join(events, on="bar_start")
        fills = trades.set_index("trade_id")
        trace["original_exit_price"] = trace.trade_id.map(fills.exit)
        trace["original_exit_time"] = trace.trade_id.map(fills.exit_time)
        trace = trace.join(encoded.join(bars), on="bar_start")
    return trades, trace, equity


def evaluate(frames, encode):
    verify_brain()
    reports = {key: [] for key in ("trades", "activations", "scores", "equity")}
    for panel, frame in frames.items():
        for date, bars in frame.groupby(frame.index.date):
            encoded = encode(bars)
            original = activations(bars, "reservoir").reservoir
            pd.testing.assert_series_equal(encoded.reservoir, original, check_names=False)
            if not {"price_forecast", "hold_long", "hold_short", "price_long", "price_short"} <= set(encoded):
                raise ValueError("capacity neuron omitted a required score")
            key = dict(panel=panel, date=date.isoformat())
            reports["scores"].append(encoded.join(bars).rename_axis("bar_start").reset_index().assign(**key))
            for delay in (0, 1):
                base, marks = replay(bars, original, delay=delay, cost=COST)
                fixed = {t.signal_time: (1 if t.side == "long" else -1) for t in base.itertuples()}
                for model, (fixed_entry, _, _) in MODELS.items():
                    trades, trace, equity = simulate(bars, encoded, delay, model, fixed if fixed_entry else None)
                    if model == "original":
                        pd.testing.assert_frame_equal(trades[TRADE_COLUMNS], base, check_dtype=False)
                        original_equity = equity.gross_equity_usd - COST * (equity.completed_trades + equity.occupancy/2)
                        np.testing.assert_array_equal(original_equity, marks)
                    if fixed_entry:
                        entry = ["signal_time", "entry_time", "side", "entry"]
                        pd.testing.assert_frame_equal(trades[entry], base[entry], check_dtype=False)
                        assert (trades.exit_time <= base.exit_time).all()
                    dims = dict(**key, delay=delay, model=model)
                    if len(trades):
                        reports["trades"].append(trades.assign(**dims))
                    if len(trace):
                        reports["activations"].append(trace.assign(**dims))
                    equity = equity.join(bars).rename_axis("bar_start").reset_index()
                    reports["equity"].append(equity.assign(**dims))
    return {name: pd.concat(parts, ignore_index=True) for name, parts in reports.items()}


def summarize(reports):
    df = normalize_trades(reports["trades"].copy())
    equity = reports["equity"]
    df = pd.concat([df, df.loc[df.panel.ne("external")].assign(panel="discovery")], ignore_index=True)
    equity = pd.concat([equity, equity.loc[equity.panel.ne("external")].assign(panel="discovery")], ignore_index=True)
    daily, aggregate = [], []
    for (panel, delay, model), bars in equity.groupby(["panel", "delay", "model"], sort=True):
        ledger = df.loc[(df.panel == panel) & (df.delay == delay) & (df.model == model)]
        activity = (ledger.groupby("session").agg(trades=("entry_index", "size"), gross=("gross_usd", "sum"))
                    .reindex(pd.Index(bars.date.unique(), name="session"), fill_value=0))
        activity["occupied_minutes"] = bars.groupby("date").occupancy.sum()
        dims = dict(panel=panel, delay=int(delay), model=model)
        sessions = bars.date.sort_values().drop_duplicates().tolist()
        for cost in COSTS:
            entire_path = equity_events(ledger, bars, cost)
            session_events = {}
            lengths = (bars.groupby("date").size() + 2*activity.trades).reindex(sessions)
            offset = 0
            for date, length in lengths.items():
                subpath = entire_path.iloc[offset:offset+length]
                opening = 0. if offset == 0 else float(entire_path.close.iat[offset-1])
                session_events[date] = drawdown_bounds(
                    subpath.assign(**{k: subpath[k] - opening for k in ("open", "low", "high", "close")})
                )
                offset += length
            assert offset == len(entire_path)
            day = activity.assign(net=activity.gross-cost*activity.trades)
            daily.extend(
                dict(**dims, cost=cost, date=date, trades=int(row.trades), net_usd=float(row.net),
                     occupied_minutes=int(row.occupied_minutes), **session_events[date])
                for date, row in day.iterrows()
            )
            aggregate.append(dict(
                **dims, cost=cost, trades=int(day.trades.sum()), net_usd=float(day.net.sum()),
                occupied_minutes=int(day.occupied_minutes.sum()), sessions=len(day),
                net_without_best_day_usd=float(day.net.sum()-day.net.max()),
                **drawdown_bounds(entire_path),
            ))
    daily = pd.DataFrame(daily)
    daily_groups = daily.groupby(["panel", "delay", "cost"], sort=False)
    summary_groups = {}
    comparisons = {
        "fixed_volume_exit": "fixed_price_exit", "full_volume_exit": "full_price_exit",
        "full_volume_entry": "full_price_entry", "full_volume_joint": "full_price_joint",
    }
    for key, group in daily_groups:
        pivot = group.pivot(index="date", columns="model", values="net_usd").sort_index()
        rng = np.random.default_rng(604)
        starts = rng.integers(len(pivot), size=(10_000, (len(pivot)+4)//5, 1))
        indices = ((starts + np.arange(5)) % len(pivot)).reshape(10_000, -1)[:, :len(pivot)]
        for model in pivot.columns:
            baselines = {"cash": 0, "original": pivot.original}
            if model in comparisons:
                baselines["price_control"] = pivot[comparisons[model]]
            summary_groups[(*key, model)] = {
                name: np.quantile(np.asarray(pivot[model]-baseline)[indices].mean(axis=1),
                                  [.025, .975]).tolist()
                for name, baseline in baselines.items()
            }
    for row in aggregate:
        key = (row["panel"], row["delay"], row["cost"], row["model"])
        row["paired_daily_mean_ci95_usd"] = summary_groups[key]

    attribution = {}
    for (panel, delay), panel_trades in df.groupby(["panel", "delay"]):
        parent = panel_trades.loc[panel_trades.model.eq("original")]
        subset = {}
        for model, (fixed_entry, _, _) in MODELS.items():
            if model == "original":
                continue
            challenger = panel_trades.loc[panel_trades.model.eq(model)]
            if fixed_entry:
                subset[model] = paired_effects(parent, challenger)
            else:
                minutes = daily.loc[
                    daily.panel.eq(panel) & daily.delay.eq(delay) & daily.model.eq(model) & daily.cost.eq(COST),
                    "occupied_minutes",
                ].sum()
                base_minutes = daily.loc[
                    daily.panel.eq(panel) & daily.delay.eq(delay) & daily.model.eq("original") & daily.cost.eq(COST),
                    "occupied_minutes",
                ].sum()
                subset[model] = full_effects(parent, challenger)
                subset[model]["occupied_minutes_change"] = int(minutes - base_minutes)
        attribution.setdefault(panel, {})[str(delay)] = subset
    return daily, aggregate, attribution


def main():
    from .neuron import encode

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    opts = parser.parse_args()
    discovery, external, provenance = load_sources(market_dir=opts.source)
    frames = {panel: group[FIELDS] for panel, group in discovery.groupby("panel", sort=False)}
    frames["external"] = external["MNQ.csv"][FIELDS]
    reports = evaluate(frames, encode)
    verify_archived(reports["trades"])
    daily, aggregate, attribution = summarize(reports)
    # The complete market score tape and trade ledger reconstruct all other
    # paths. Keep the original open-position path as a separate diagnostic.
    reports.pop("equity")
    write_outputs(reports, opts.output)
    daily.to_csv(opts.output/"daily.csv", index=False)
    (opts.output/"results.json").write_text(json.dumps(aggregate, indent=2)+"\n")
    (opts.output/"attribution.json").write_text(json.dumps(attribution, indent=2)+"\n")
    provenance["neuron_sha256"] = hashlib.sha256(Path(__file__).with_name("neuron.py").read_bytes()).hexdigest()
    (opts.output/"source.json").write_text(json.dumps(provenance, indent=2)+"\n")


if __name__ == "__main__":
    main()
