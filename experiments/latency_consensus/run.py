"""Replay the frozen latency-consensus learner in chronological session batches."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from experiments.barrier_response.run import HOLD, ONE, equity_path, events
from experiments.capacity.neuron import encode
from experiments.hold_work.sources import load_sources
from .neuron import Consensus

HURDLE = 3.
DIMENSIONS = {"unconditional": 1, "geometry": 2, "consensus": 4}
POLICIES = (*DIMENSIONS, "midpoint", "follow", "cash")
COSTS = (3, 6, 9)


def execution(bars, signal, delay):
    """Resolve an actual order independently of its alternative latency."""
    index = bars.index
    due = signal + (1+delay)*ONE
    target_exit = due + HOLD
    entry_pos = index.get_loc(signal) + 1
    for j in range(delay+1):
        i = entry_pos + j
        if i == len(index):
            return {"status": "cancelled_gap", "release": index[-1]+ONE}
        if index[i] != signal + (1+j)*ONE:
            return {"status": "cancelled_gap", "release": index[i]}
    i = entry_pos + delay
    entry = bars.open.iat[i]
    exit_pos = i+1
    while exit_pos < len(index) and index[exit_pos] < target_exit and index[exit_pos]-index[exit_pos-1] == ONE:
        exit_pos += 1
    if exit_pos == len(index):
        raise ValueError("session ended with a filled exposure")
    finish = index[exit_pos]
    gap = finish != target_exit or finish-index[exit_pos-1] != ONE
    return dict(status="gap_exit" if gap else "scheduled_exit", release=finish,
                entry_time=due, exit_time=finish, entry=float(entry), exit=float(bars.open.iat[exit_pos]))


def projections(bars, memory):
    """Finish a day's signal decisions using only the previous-day memories."""
    encoded = encode(bars)
    signals = events(bars, encoded)
    gaps = ~bars.index.to_series().diff().eq(ONE)
    background = bars.volume.rename("background").groupby(gaps.cumsum().to_numpy()).transform(
        lambda s: s.ewm(span=32, adjust=False).mean().shift()
    )
    cutoff = bars.index[0].replace(hour=15, minute=55)
    for e in signals.loc[signals.event.eq("retained")].itertuples():
        if e.signal + 2*ONE + HOLD > cutoff:
            continue
        touch = bars.loc[e.signal]
        scale = max(.25, float(encoded.at[e.signal, "scale"]))
        direction = int(e.side)
        extreme = touch.low if direction == 1 else touch.high
        adverse = max(0., direction*(e.next_close_barrier-extreme))
        recovery = direction*(touch.close-e.next_close_barrier)
        location = (recovery-adverse)/(recovery+adverse+.25)
        participation = (touch.volume-background[e.signal])/(touch.volume+background[e.signal]+2.)
        u = np.array([1., location, participation, location*participation])
        if not np.isfinite(u).all():
            raise ValueError("missing causal feature on an eligible boundary touch")

        row = dict(
            signal=e.signal, issued=e.issued_bar, direction=direction, barrier=e.next_close_barrier,
            scale=scale, adverse=adverse, recovery=recovery, location=location,
            participation=participation, volume=float(touch.volume), prior_mean_volume=float(background[e.signal]),
            trained_sessions=len(memory.sessions),
        )
        actions = {"follow": 1, "cash": 0}
        for name, dimension in DIMENSIONS.items():
            low, high, center = memory.project(u, scale, dimension)
            row.update({f"{name}_low": low, f"{name}_high": high, f"{name}_midpoint": center})
            actions[name] = 1 if low > HURDLE else -1 if high < -HURDLE else 0
        center = row["consensus_midpoint"]
        actions["midpoint"] = 1 if center > HURDLE else -1 if center < -HURDLE else 0
        row.update({f"{name}_action": action for name, action in actions.items()})
        yield row, u, actions


def replay_day(bars, memory, source, date):
    busy_until = {(delay, policy): bars.index[0] for delay in (0, 1) for policy in POLICIES}
    forecasts, trades, features, normalized_returns = [], [], [], []
    # Materialize every inference before resolving any future fill or label.
    issued = list(projections(bars, memory))
    for row, feature, actions in issued:
        row.update(source=source, date=date)
        paired = []
        for delay in (0, 1):
            outcome = execution(bars, row["signal"], delay)
            suffix = f"_{delay}"
            row[f"status{suffix}"] = outcome["status"]
            filled = "entry" in outcome
            if filled:
                progress = row["direction"]*(outcome["exit"]-outcome["entry"])
                for field in ("entry_time", "exit_time", "entry", "exit"):
                    row[field + suffix] = outcome[field]
                row[f"realized_points{suffix}"] = progress
                if outcome["status"] == "scheduled_exit":
                    paired.append(progress/row["scale"])
            for policy, action in actions.items():
                accepted = action != 0 and row["signal"] >= busy_until[delay, policy]
                row[f"{policy}_accepted{suffix}"] = accepted
                if accepted:
                    busy_until[delay, policy] = outcome["release"]
                    if filled:
                        side = action * row["direction"]
                        duration = int(bars.index.get_loc(outcome["exit_time"]) - bars.index.get_loc(outcome["entry_time"]))
                        trades.append(dict(
                            source=source, date=date, policy=policy, delay=delay, signal=row["signal"],
                            side=side, relative_action=action, gross_usd=2*action*progress,
                            observed_minutes=duration, **outcome,
                        ))
        row["common_label"] = len(paired) == 2
        if row["common_label"]:
            features.append(feature)
            normalized_returns.append(paired)
        forecasts.append(row)
    memory.observe_session(features, normalized_returns)
    return forecasts, trades


def spearman(a, b):
    x, y = rankdata(a), rankdata(b)
    if len(x) < 2 or not np.std(x) or not np.std(y):
        return None
    return float(np.corrcoef(x,y)[0,1])


def evaluate(projections, trades, calendars, tapes):
    summaries, daily = {}, []
    by_source = projections.groupby("source", sort=False)
    for source, events_frame in by_source:
        dates = calendars[source]
        n = len(dates)
        starts = np.random.default_rng(604).integers(n,size=(10_000,(n+4)//5,1))
        indices = ((starts+np.arange(5))%n).reshape(10_000,-1)[:,:n]
        common = events_frame.loc[events_frame.common_label].copy()
        common["mean_points"] = common[["realized_points_0","realized_points_1"]].mean(axis=1)
        ranking = {
            policy: {label: spearman(common[f"{policy}_midpoint"], common[label])
                     for label in ("realized_points_0", "realized_points_1", "mean_points")}
            for policy in DIMENSIONS
        }
        learned = common.loc[common.trained_sessions.gt(0)]
        ranking_after_warmup = {
            policy: {label: spearman(learned[f"{policy}_midpoint"], learned[label])
                     for label in ("realized_points_0", "realized_points_1", "mean_points")}
            for policy in DIMENSIONS
        }
        source_summary = summaries[source] = {
            "sessions": n, "clock_eligible_signals": len(events_frame), "common_labels": len(common),
            "trained_common_labels": len(learned), "spearman": ranking,
            "spearman_after_warmup": ranking_after_warmup,
        }
        for delay in (0, 1):
            report, day6 = {}, {}
            for policy in POLICIES:
                t = trades.loc[trades.source.eq(source) & trades.delay.eq(delay) & trades.policy.eq(policy)]
                gross = t.gross_usd
                row = report[policy] = dict(
                    trades=len(t), active_sessions=int(t.date.nunique()), gross_usd=float(gross.sum()),
                    follow=int(t.relative_action.eq(1).sum()), fade=int(t.relative_action.eq(-1).sum()),
                    long=int(t.side.eq(1).sum()), short=int(t.side.eq(-1).sum()),
                    occupied_observed_minutes=int(t.observed_minutes.sum()),
                    actionable_signals=int(events_frame[f"{policy}_action"].ne(0).sum()),
                    submitted_orders=int(events_frame[f"{policy}_accepted_{delay}"].sum()),
                    gap_exits=int(t.status.eq("gap_exit").sum()), costs={},
                )
                row["cancelled_orders"] = row["submitted_orders"] - len(t)
                for cost in COSTS:
                    net = gross-cost
                    daily_model = net.groupby(t.date).sum().reindex(dates,fill_value=0.)
                    if cost == 6:
                        day6[policy] = daily_model.to_numpy()
                    row["costs"][cost] = dict(
                        net_usd=float(net.sum()), expectancy_usd=float(net.mean()) if len(net) else None,
                        without_best_trade_usd=float(net.sum()-net.max()) if len(net) else 0.,
                        without_top_three_positive_trades_usd=float(net.sum()-net.nlargest(3).clip(lower=0).sum()),
                        without_best_day_usd=float(net.sum()-daily_model.max()),
                        **equity_path(t,tapes[source],"side",cost),
                    )
                    for date, value in daily_model.items():
                        daily.append(dict(source=source,delay=delay,policy=policy,cost=cost,date=date,net_usd=float(value)))
            for policy, metrics in report.items():
                paired = metrics["paired_daily_ci95_usd"] = {}
                for control in ("cash","unconditional","geometry","midpoint","follow"):
                    if control != policy:
                        diff = day6[policy] - day6[control]
                        paired[control] = np.quantile(diff[indices].mean(axis=1),[.025,.975]).tolist()
                if policy == "consensus":
                    metrics["passes"] = bool(
                        metrics["trades"] >= 30 and metrics["active_sessions"] >= 10
                        and metrics["costs"][9]["without_best_trade_usd"] > 0
                        and metrics["costs"][6]["intrabar_drawdown_upper"] < 1500
                        and min(paired[control][0] for control in ("cash","unconditional","geometry")) > 0
                    )
            source_summary[str(delay)] = report
    return summaries, pd.DataFrame(daily)


def run(market, destination):
    discovery, external, source_receipt = load_sources(market_dir=market)
    calendars, tapes = {}, {}
    forecasts, ledger = [], []
    for source, frame in (("discovery40", discovery), ("external60", external["MNQ.csv"])):
        memory = Consensus()
        tapes[source] = {str(date): b for date,b in frame.groupby(frame.index.date,sort=True)}
        calendars[source] = list(tapes[source])
        for date, bars in tapes[source].items():
            predictions, trades = replay_day(bars, memory, source, date)
            forecasts.extend(predictions)
            ledger.extend(trades)
    forecasts, ledger = pd.DataFrame(forecasts), pd.DataFrame(ledger)
    summary, daily = evaluate(forecasts,ledger,calendars,tapes)
    destination.mkdir(parents=True,exist_ok=True)
    for name, table in (("projections",forecasts),("trades",ledger)):
        table.to_csv(destination/f"{name}.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    daily.to_csv(destination/"daily.csv",index=False)
    summary["qualifies"] = all(summary[source][str(delay)]["consensus"]["passes"]
                               for source in calendars for delay in (0,1))
    (destination/"summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n")
    source_receipt["neuron_sha256"] = hashlib.sha256(Path(__file__).with_name("neuron.py").read_bytes()).hexdigest()
    source_receipt["registered_commit"] = "62fe3f5"
    (destination/"source.json").write_text(json.dumps(source_receipt,indent=2)+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("market",type=Path)
    parser.add_argument("output",type=Path)
    arguments = parser.parse_args()
    run(arguments.market,arguments.output)
