"""Frozen inputs and neurons, paired entry replay followed by endogenous re-entry."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from circuit import directional_state
from simulator import simulate
from chart import render

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tick_exit"))
from experiment import get_panels, metrics, FOCUS
from session import CORE, FRICTION, activations, ledger, minute, replay, verify_brain

CONTROLS = ("volume", "price")
KEY = ["entry_time","side"]


def panel_name(day):
    if day == FOCUS:
        return "nov19"
    return "november_other13" if day.startswith("2026-11") else "earlier20"


def match(base, edited):
    return base.merge(edited, how="outer", on=KEY, suffixes=("_base","_edit"), indicator=True,
                      validate="one_to_one").assign(delta=lambda t: t.net_usd_edit - t.net_usd_base)


def fixed_stats(t):
    assert (t._merge == "both").all()
    result = {}
    for name, subset in [("original_losers",t[t.net_usd_base<0]),
                         ("original_winners",t[t.net_usd_base>0]),
                         ("original_flat",t[t.net_usd_base==0])]:
        delta = subset.delta
        result[name] = dict(count=len(subset), improved_usd=float(delta.clip(lower=0).sum()),
                            damaged_usd=float(-delta.clip(upper=0).sum()), net_delta=float(delta.sum()))
    return result


def full_stats(t):
    shared = t[t._merge == "both"]
    add = t[t._merge == "right_only"]
    missing = t[t._merge == "left_only"]
    result = {"shared":len(shared),"shared_delta":float(shared.delta.sum()),
              "missed":len(missing),"missed_original_net":float(missing.net_usd_base.sum()),
              "extra_friction":float((len(add)-len(missing))*FRICTION)}
    for label,group in [("reentries",add[add.same_episode_reentry_edit.eq(True)]),
                        ("other_added",add[~add.same_episode_reentry_edit.eq(True)])]:
        result[label] = dict(count=len(group),gross=float(group.gross_usd_edit.sum()),
                             costs=len(group)*FRICTION,net=float(group.net_usd_edit.sum()))
    gross_delta = t.gross_usd_edit.sum()-t.gross_usd_base.sum()
    observed = t.net_usd_edit.sum()-t.net_usd_base.sum()
    assert np.isclose(observed,gross_delta-result["extra_friction"])
    assert np.isclose(observed, result["shared_delta"]-result["missed_original_net"]
                      +result["reentries"]["net"]+result["other_added"]["net"])
    return dict(**result,gross_delta=float(gross_delta))


def classify(trades,raw):
    flags = []
    prev = None
    for t in trades.itertuples():
        side = 1 if t.side == "long" else -1
        flags.append(prev is not None and prev.reason=="hold" and prev.side==t.side
                     and (side*raw.loc[prev.exit_time:t.signal_time]>0).all())
        prev = t
    return trades.assign(same_episode_reentry=flags)


def case(row):
    return dict(date=str(row.entry_time.date()), entry=minute(row.entry_time),side=row.side,
                original_exit=minute(row.exit_time_base),edited_exit=minute(row.exit_time_edit),
                original_net=float(row.net_usd_base),edited_net=float(row.net_usd_edit),delta=float(row.delta))


def numbers(s):
    return [None if pd.isna(x) else float(x) for x in s]


def run(scratch,out):
    out.mkdir(exist_ok=True,parents=True)
    verify_brain()
    states, results, equity, charts = {}, {}, {}, {}
    modes=["original",*[f"{phase}_{ctrl}" for phase in ["fixed","full"] for ctrl in CONTROLS]]
    trace_frames = []
    for source,bars in get_panels(scratch).items():
        original_panel = []
        for day,b in bars.groupby(bars.index.date):
            day=str(day)
            a=activations(b,"reservoir")
            base,mark=replay(b,a.reservoir,delay=0,cost=FRICTION)
            original_panel.append(base)
            results[day,"original"]=classify(base,a.reservoir)
            equity[day,"original"]=mark
            heads={}
            trace=a[["reservoir","effort","scale"]].copy()
            for ctrl in CONTROLS:
                for side in [1,-1]:
                    col = "long" if side==1 else "short"
                    state=directional_state(b,a,side,with_volume=(ctrl=="volume"))
                    heads[ctrl,side]=state.hold
                    trace=trace.join(state.add_prefix(f"{ctrl}_{col}_"))
            states[day]=(b,a.reservoir,heads)
            trace_frames.append(trace)
            cells=[[minute(i),*ohlcv,*numbers(v)] for i,ohlcv,v in zip(b.index,b.to_numpy().tolist(),
                    a[["reservoir","stock","charge","signed_release"]].to_numpy(),strict=True)]
            charts[day]=dict(date=day,bars=cells,layers={"original":{"trades":ledger(base),"hold":[None]*len(b)}})
        expected=pd.read_csv(CORE/source/"reservoir-delay0.csv")
        actual=pd.concat(original_panel,ignore_index=True)
        for col in ["signal_time","entry_time","exit_time"]:
            assert pd.to_datetime(expected[col],utc=True).equals(pd.to_datetime(actual[col],utc=True))
        assert list(expected.side)==list(actual.side)
        np.testing.assert_allclose(actual.net_usd.astype(float),expected.net_usd-3)

    # Fixed cohort is complete before any unconstrained portfolio replay.
    for phase in ["fixed","full"]:
        for day,(b,raw,heads) in states.items():
            base=results[day,"original"]
            entries={t.signal_time:1 if t.side=="long" else -1 for t in base.itertuples()}
            for ctrl in CONTROLS:
                mode=f"{phase}_{ctrl}"
                t,m,h=simulate(b,raw,heads[ctrl,1],heads[ctrl,-1],entries if phase=="fixed" else None)
                if phase=="fixed":
                    assert list(zip(t.entry_time,t.side,t.entry))==list(zip(base.entry_time,base.side,base.entry))
                    assert (t.exit_time.to_numpy() <= base.exit_time.to_numpy()).all()
                assert np.isclose(t.net_usd.sum(),m.iloc[-1])
                for tr in t.itertuples():
                    sl=(h.index>=tr.entry_time)&(h.index<tr.exit_time)
                    np.testing.assert_allclose(h[sl],heads[ctrl,1 if tr.side=="long" else -1][sl],equal_nan=True)
                results[day,mode]=classify(t,raw)
                equity[day,mode]=m
                charts[day]["layers"][mode]=dict(trades=ledger(t),hold=numbers(h))

    all_trades={m:pd.concat([results[d,m] for d in states],ignore_index=True) for m in modes}
    report={}
    for group in ["earlier20","nov19","november_other13","all_november"]:
        dates=[d for d in states if panel_name(d)==group or (group=="all_november" and d.startswith("2026-11"))]
        base=pd.concat([results[d,"original"] for d in dates],ignore_index=True)
        report[group]={}
        for m in modes:
            trades=pd.concat([results[d,m] for d in dates],ignore_index=True)
            s=metrics(trades,[equity[d,m] for d in dates])
            if m!="original":
                pairs=match(base,trades)
                s["attribution"]=fixed_stats(pairs) if m.startswith("fixed") else full_stats(pairs)
            report[group][m]=s
    pairs=match(all_trades["original"],all_trades["fixed_volume"])
    extremes={"improvement":case(pairs.loc[pairs.delta.idxmax()]),
              "damaged_winner":case(pairs.loc[pairs[pairs.net_usd_base>0].delta.idxmin()])}
    for m,t in all_trades.items():
        t.to_csv(out/f"{m}-trades.csv",index=False)
    pd.concat(trace_frames).to_csv(out/"neurons.csv.gz",compression={"method":"gzip","mtime":0})
    pd.DataFrame([dict(date=d,mode=m,net=equity[d,m].iloc[-1],trades=len(results[d,m]))
                  for d in states for m in modes]).to_csv(out/"daily.csv",index=False)
    (out/"results.json").write_text(json.dumps(dict(panels=report,extremes=extremes),indent=2,allow_nan=False)+"\n")
    render(list(charts.values()),extremes,out/"hold-chart.html")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("scratch",type=Path)
    p.add_argument("output",type=Path)
    args=p.parse_args()
    run(args.scratch,args.output)
