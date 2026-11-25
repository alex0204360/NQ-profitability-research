"""Path-risk forecasting and funded-position replay with chronological updates."""
import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from replay_lab import LAB, activations, bounds, paired, panels
from risk_head import CFG, INITIAL, Q, Reserve, RiskCapacitor
sys.path.insert(0,str(LAB/"adverse_impact"))
from simulator import simulate


def summarize(labels):
    models={}
    day=labels.origin.dt.date
    for col in ["band","physical","rolling"]:
        error=labels.travel-labels[col]
        loss=np.maximum(Q*error,(Q-1)*error)
        coverage=(error<=0).groupby(day).mean()
        models[col]=dict(n=len(labels),coverage=float((error<=0).mean()),
                         mean_halfwidth=float(labels[col].mean()),quantile_loss=float(loss.mean()),
                         worst_overflow=float(error.clip(lower=0).max()),
                         daily_coverage_range=[float(coverage.min()),float(coverage.max())],
                         daily_coverage_block=paired(coverage,0.))
    rival=min(models[c]["quantile_loss"] for c in ("physical","rolling"))
    score=models["band"]
    return dict(models=models,risk_screen=.87<=score["coverage"]<=.93 and score["quantile_loss"]<=1.05*rival,
                improvement_over_both=score["quantile_loss"]<rival)


def run(frames,out,clock=False):
    from overlap import ExposureClock
    out.mkdir(parents=True,exist_ok=False)
    report={}
    all_labels=[]
    all_trades=[]
    states=[]
    daily=[]
    for panel,bars in frames.items():
        memory=ExposureClock() if clock else RiskCapacitor()
        policy=Reserve()
        physical_policy=Reserve()
        physical_ledgers=[]
        labels=[]
        trades=[]
        for day,b in bars.groupby(bars.index.date):
            a=activations(b,"reservoir")
            r,l=memory.session(b,a)
            labels.append(l)
            states.append(r.assign(panel=panel))
            policy.prepare(b,r.band)
            t,m,h=simulate(b,a.reservoir,a.reservoir,-a.reservoir,policy=policy)
            trades.append(t)
            physical_policy.prepare(b,r.physical)
            pt,_,_=simulate(b,a.reservoir,a.reservoir,-a.reservoir,policy=physical_policy)
            physical_ledgers.append(pt)
            assert np.isclose(t.net_usd.sum(),m.iloc[-1])
            daily.append(dict(panel=panel,date=str(day),trades=len(t),net=t.net_usd.sum(),
                              coverage=float((l.travel<=l.band).mean()),n=len(l)))
        l=pd.concat(labels,ignore_index=True)
        t=pd.concat([t for t in trades if len(t)],ignore_index=True) if any(len(t) for t in trades) else trades[0]
        assert np.isclose(policy.realized,t.net_usd.sum())
        excess=(l.travel>l.band).sum()-len(l)*(1-Q)
        drift=(memory.log_scale-math.log(INITIAL))/(CFG["log_gain"]/(CFG["horizon"] if clock else 1))
        assert abs(excess-drift)<1e-8
        row=summarize(l)
        row["calibration_identity_error"]=float(abs(excess-drift))
        row["final_multiplier"]=math.exp(memory.log_scale)
        row["reserve_policy"]=dict(**bounds(bars,t),trades=len(t),expectancy=policy.realized/len(t) if len(t) else None,
            net_9_fixed_ledger=policy.realized-3*len(t),without_best_day=policy.realized-max(x["net"] for x in daily if x["panel"]==panel),
            unfunded_bar_closes=policy.blocks)
        physical_t=pd.concat([part for part in physical_ledgers if len(part)],ignore_index=True)
        row["static_reserve_control"]=dict(**bounds(bars,physical_t),trades=len(physical_t))
        report[panel]=row
        all_labels.append(l.assign(panel=panel))
        all_trades.append(t.assign(panel=panel))
    (out/"scorecard.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    pd.concat(states).to_csv(out/"traces.csv.gz",compression={"method":"gzip","mtime":0})
    pd.concat(all_labels).to_csv(out/"observations.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    pd.concat(all_trades).to_csv(out/"trades.csv",index=False)
    pd.DataFrame(daily).to_csv(out/"daily.csv",index=False)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("scratch",type=Path);p.add_argument("out",type=Path)
    p.add_argument("--track",choices=["discovery","replication"],default="discovery")
    p.add_argument("--clock",action="store_true")
    args=p.parse_args();run(panels(args.scratch,args.track),args.out,args.clock)
