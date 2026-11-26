"""Replay matched exits first and then allow the trading policy to re-enter."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
sys.path[:0] = [str(LAB.parents[1]), str(LAB/"adverse_impact")]
from study import case, classify, fixed_stats, full_stats, match, numbers
from simulator import simulate
from session import activations, ledger, minute, replay, verify_brain
from experiments.reservoir_lab.trade_memory.chart import render
sys.path.insert(0, str(LAB/"capacitor_bridge"))
from replay_lab import panels, bounds
sys.path.insert(0, str(LAB/"volume_auction"))
from impulse import encode
from timing import timed
from exit_head import ExitHead, inputs
from restart import RestartHead


def comparison(a, b):
    delta = np.asarray(a) - np.asarray(b)
    rng = np.random.default_rng(604)
    n = len(delta)
    starts = rng.integers(n, size=(10000, (n+4)//5, 1))
    index = ((starts + np.arange(5)) % n).reshape(10000, -1)[:, :n]
    return np.quantile(delta[index].mean(axis=1), [.025, .975]).tolist()


def evaluate(frames, out, extra=None, draw_chart=False):
    verify_brain()
    out.mkdir(exist_ok=True, parents=True)
    report, daily, ledgers, charts, examples, events = {}, [], [], [], [], []
    for panel, frame in frames.items():
        day_trades = {}
        for date, b in frame.groupby(frame.index.date):
            a = activations(b, "reservoir")
            raw = a.reservoir
            original, _ = replay(b, raw, cost=6.)
            rows = {"original": classify(original, raw)}
            signals = {t.signal_time: 1 if t.side=="long" else -1 for t in original.itertuples()}
            features = inputs(b)
            chart = {"date": str(date), "layers":{}}
            if draw_chart:
                chart["bars"] = [[minute(ts), *ohlcv, *numbers(neurons)] for ts, ohlcv, neurons in
                    zip(b.index, b[["open","high","low","close","volume"]].to_numpy(),
                        a[["reservoir","stock","charge","signed_release"]].to_numpy(), strict=True)]
                chart["layers"]["original"] = {"trades":ledger(original), "hold":[None]*len(b)}
            for fixed in (True, False):
                for prefix, cls in (("", ExitHead), ("restart_", RestartHead)):
                    for volume in (True, False):
                        name = ("fixed_" if fixed else "") + prefix + ("volume" if volume else "price")
                        head = cls(features, volume)
                        t, m, h = simulate(b, raw, raw, -raw, signals if fixed else None, head)
                        if fixed:
                            pd.testing.assert_frame_equal(original[["entry_time","side","entry"]], t[["entry_time","side","entry"]],check_dtype=False)
                            assert (t.exit_time <= original.exit_time).all()
                        assert t.net_usd.sum() == m.iat[-1]
                        rows[name] = classify(t, raw)
                        if draw_chart:
                            chart["layers"][name] = {"trades":ledger(t), "hold":numbers(h)}
                        if name in ("fixed_volume","fixed_restart_volume"):
                            events.extend((panel,name,b.index[i],side,e,*cells) for i,side,e,*cells in head.activations)
            impulse = encode(b)
            for name in ("weighted","equal_mass","v08_sym"):
                rows[name], _ = timed(b, impulse[name])
            if extra:
                rows.update(extra(b))
            for name, t in rows.items():
                day_trades.setdefault(name, []).append(t)
                if len(t):
                    ledgers.append(t.assign(panel=panel,model=name))
                daily.append(dict(panel=panel,date=str(date),model=name,net=float(t.net_usd.sum()),trades=len(t)))
            if draw_chart:
                charts.append(chart)
                examples.append(match(original, rows["fixed_restart_volume"]))
        groups = {panel:frame}
        if panel=="november14":
            mask = frame.index.strftime("%Y-%m-%d")=="2026-11-19"
            groups.update(nov19=frame.loc[mask],other13=frame.loc[~mask])
        for group, bars in groups.items():
            report[group] = {}
            dates = set(map(str,bars.index.date))
            trade_rows = {name:pd.concat([t for t in parts if len(t)],ignore_index=True) if any(map(len,parts)) else parts[0] for name,parts in day_trades.items()}
            trade_rows = {name:t[t.entry_time.isin(bars.index)] for name,t in trade_rows.items()}
            day = pd.DataFrame(daily).query("panel==@panel and date in @dates").pivot(index="date",columns="model",values="net")
            base = trade_rows["original"]
            for name,t in trade_rows.items():
                stats = bounds(bars,t)
                net = stats["net"]
                stats.update(trades=len(t), expectancy=net/len(t) if len(t) else None, net_at_9=net-3*len(t),
                             without_best_day=net-day[name].max(), sessions=len(day),interval_vs_cash=comparison(day[name],0),
                             interval_vs_original=comparison(day[name],day.original))
                if name.startswith("fixed_"):
                    stats["attribution"] = fixed_stats(match(base,t))
                if name in ("volume","price","restart_volume","restart_price"):
                    stats["attribution"] = full_stats(match(base,t))
                if name in ("volume","restart_volume","auction"):
                    control = {"volume":"price","restart_volume":"restart_price","auction":"auction_equal"}[name]
                    stats["interval_vs_control"] = comparison(day[name],day[control])
                    stats["passes"] = bool(len(t)>=50 and len(day)>=20 and stats["net_at_9"]>0 and stats["intraminute_max_dd"]<1500 and
                        min(stats[k][0] for k in ("interval_vs_cash","interval_vs_original","interval_vs_control"))>0)
                    if name=="auction":
                        for control_name in ("always_long","open_only"):
                            interval = comparison(day[name],day[control_name])
                            stats["interval_vs_"+control_name] = interval
                            stats["passes"] &= interval[0]>0
                report[group][name] = stats
    if draw_chart:
        pairs = pd.concat(examples,ignore_index=True)
        winners = pairs[pairs.net_usd_base>0]
        extremes = {"improvement":case(pairs.loc[pairs.delta.idxmax()]), "damaged_winner":case(winners.loc[winners.delta.idxmin()])}
        if extremes["improvement"]["delta"]<=0:
            extremes["improvement"]=None
        if extremes["damaged_winner"]["delta"]>=0:
            extremes["damaged_winner"]=None
        report["chart_cases"] = extremes
        modes = {key:(key.replace("_"," ").title(), "Original entries fixed." if key.startswith("fixed") else "Full strategy.") for key in charts[0]["layers"]}
        render(charts,extremes,out/"replay.html",policies=modes,title="MNQ adverse-response evidence",default_mode="restart_volume",
               fixed_mode="fixed_restart_volume",reset_modes=[m for m in modes if m!="original"],score_label="experimental stopping margin",
               explanation="<p>Evidence cells compound adverse bar bodies. Hold value is positive while the original sign survives and adverse evidence is under eight. Case buttons compare identical entries.</p>")
    (out/"results.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    pd.DataFrame(daily).to_csv(out/"daily.csv",index=False)
    pd.concat(ledgers,ignore_index=True).to_csv(out/"trades.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    pd.DataFrame(events,columns=["panel","model","bar_start","side","evidence","slow","medium","fast"]).to_csv(out/"activations.csv.gz",index=False,compression={"method":"gzip","mtime":0})


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("scratch",type=Path)
    p.add_argument("out",type=Path)
    p.add_argument("--extended",action="store_true")
    p.add_argument("--external",action="store_true")
    args=p.parse_args()
    extra=None
    if args.extended:
        from auction import strategies
        extra=strategies
    if args.external:
        from source import external
        frames=external(args.scratch/"response-evidence",args.out)
    else:
        frames=panels(args.scratch,"discovery")
        if args.extended:
            from known_day import november25
            frames.update(panels(args.scratch,"replication"),nov25=november25(args.scratch))
    evaluate(frames,args.out,extra,draw_chart=not args.external)
    if args.external:
        from synchrony import evaluate_pair
        evaluate_pair(frames["external"],args.scratch/"response-evidence",args.out)
