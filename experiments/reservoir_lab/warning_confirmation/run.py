"""Replay the frozen confirmation policy and its immediate and delay controls."""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
sys.path[:0] = [str(LAB.parents[1]), str(LAB / "tick_exit"), str(LAB / "adverse_impact")]
from experiment import get_panels, metrics
from session import activations, ledger, minute, replay, verify_brain
from simulator import simulate
from study import case, classify, fixed_stats, full_stats, match, numbers
from experiments.reservoir_lab.failed_recovery.circuit import directional_state
from experiments.reservoir_lab.trade_memory.chart import render
from experiments.reservoir_lab.trade_memory.routing import TradeMemory
from experiments.reservoir_lab.warning_confirmation.circuit import WarningMemory

POLICIES = {"original": ("Original reservoir", "The original forecast controls the position.")}
for fixed in (True, False):
    for policy, detail in [
        ("immediate", "Exit on the first discretionary warning."),
        ("delay", "Wait one completed bar, then exit regardless of recovery."),
        ("confirm", "Exit if the next completed close fails to reclaim the warning close."),
    ]:
        prefix = "fixed_" if fixed else ""
        label = "Identical entries" if fixed else "Full strategy"
        POLICIES[prefix + policy] = (f"{label} · {policy}", detail)


def setup(bars):
    a = activations(bars, "reservoir")
    states = {s: directional_state(bars, a, s) for s in (1, -1)}
    return a, {s: state.new_shock.to_numpy() for s, state in states.items()}, states


def examples(pairs):
    winners = pairs[pairs.net_usd_base > 0]
    return {"improvement": case(pairs.loc[pairs.delta.idxmax()]),
            "damaged_winner": case(winners.loc[winners.delta.idxmin()])}


def run(scratch, out):
    verify_brain()
    out.mkdir(parents=True, exist_ok=True)
    days, charts, events, trades, equity = {}, [], [], {}, {}
    for panel, frame in get_panels(scratch).items():
        for date, bars in frame.groupby(frame.index.date):
            day = str(date)
            assert day <= "2026-11-20"
            days[day] = "earlier20" if panel == "discovery" else "november14"
            a, shocks, states = setup(bars)
            raw = a.reservoir
            candles = [[minute(ts), *ohlcv, *numbers(neurons)]
                       for ts, ohlcv, neurons in zip(bars.index, bars.to_numpy().tolist(),
                           a[["reservoir","stock","charge","signed_release"]].to_numpy(), strict=True)]
            layers = {}
            original, marks = replay(bars, raw, cost=6.)
            entries = {t.signal_time: 1 if t.side == "long" else -1 for t in original.itertuples()}
            for mode in POLICIES:
                policy = mode.removeprefix("fixed_")
                if mode == "original":
                    t, m, hold = original, marks, pd.Series(float("nan"), index=bars.index)
                else:
                    fixed = mode.startswith("fixed_")
                    head = (TradeMemory(a, shocks, True, True) if policy == "immediate"
                            else WarningMemory(a, shocks, policy))
                    t, m, hold = simulate(bars, raw, states[1].hold, states[-1].hold,
                                          fixed_signals=entries if fixed else None, policy=head)
                    if fixed:
                        assert t[["entry_time","side"]].equals(original[["entry_time","side"]])
                        assert (t.exit_time <= original.exit_time).all()
                    if policy != "immediate":
                        events.extend((day, mode, *row) for row in head.events)
                assert m.iloc[-1] == t.net_usd.sum()
                trades[day,mode], equity[day,mode] = classify(t,raw), m
                layers[mode] = {"trades": ledger(t), "hold": numbers(hold)}
            charts.append({"date": day, "bars": candles, "layers": layers})

    all_trades = {mode: pd.concat([trades[d,mode] for d in sorted(days)], ignore_index=True)
                  for mode in POLICIES}
    for mode, old in [("original","original"), ("fixed_immediate","fixed_local"), ("immediate","both")]:
        path = LAB / "trade_memory" / "results" / f"{old}.csv"
        assert all_trades[mode].to_csv(index=False) == path.read_text(), f"parent parity {mode}"

    panels = {g: sorted(d for d,v in days.items() if v == g) for g in ("earlier20","november14")}
    assert len(panels["earlier20"]) == 20 and len(panels["november14"]) == 14
    panels["nov19"] = ["2026-11-19"]
    panels["other13"] = [d for d in panels["november14"] if d != "2026-11-19"]
    report = {}
    for group, dates in panels.items():
        led = {mode: pd.concat([trades[d,mode] for d in dates], ignore_index=True) for mode in POLICIES}
        rows = {mode: metrics(led[mode], [equity[d,mode] for d in dates]) for mode in POLICIES}
        for mode in ("fixed_immediate", "fixed_delay", "fixed_confirm"):
            rows[mode]["original_outcomes"] = fixed_stats(match(led["original"], led[mode]))
        for base in ("immediate", "delay", "original"):
            rows["confirm"]["versus_" + base] = full_stats(match(led[base], led["confirm"]))
        report[group] = rows
    extremes = examples(match(all_trades["original"], all_trades["fixed_confirm"]))
    report["extremes_against_original"] = extremes
    report["extremes_against_immediate"] = examples(match(all_trades["fixed_immediate"], all_trades["fixed_confirm"]))
    report["passes_screen"] = all(report[g]["confirm"]["net"] > max(report[g][m]["net"] for m in ("immediate","delay"))
        and report[g]["confirm"]["marked_drawdown"] <= report[g]["immediate"]["marked_drawdown"]
        for g in ("earlier20","november14"))
    (out/"results.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    pd.concat(all_trades, names=["mode","row"]).droplevel("row").to_csv(out/"trades.csv")
    pd.DataFrame(events, columns=["day","mode","bar_start","warning_bar_start","event","displacement"]).to_csv(out/"events.csv", index=False)
    pd.DataFrame([{ "day": d, **{m:equity[d,m].iloc[-1] for m in POLICIES}} for d in sorted(days)]).to_csv(out/"daily.csv",index=False)
    render(sorted(charts,key=lambda c:c["date"]), extremes, out/"replay.html", policies=POLICIES,
           title="Reservoir Warning Confirmation", default_mode="confirm", fixed_mode="fixed_confirm",
           reset_modes=[m for m in POLICIES if m != "original"], score_label="experimental stopping score",
           explanation="<p>Positive hold favors the current position. A warning stores its close and waits for one more completed bar. A long must close above that level to reclaim it. A short must close below. A failed reclaim requests the next open. The original forecast exit and 15:55 cutoff still apply. The case buttons compare the original and confirmation exits at identical entries.</p>")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scratch", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.scratch,args.output)
