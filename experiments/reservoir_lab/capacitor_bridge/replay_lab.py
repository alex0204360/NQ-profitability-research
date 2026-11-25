"""Frozen circuit replays. Labels and money statistics stay outside the neurons."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
LAB=HERE.parent
sys.path[:0]=[str(LAB/"minute_observatory"),str(LAB/"tick_exit")]
from risk import bounds
from experiment import get_panels
from session import verify_brain, activations, replay
from data import regular_hours
from evaluate import paired
from capacitor import circuit


def panels(scratch,track):
    if track=="replication":
        path=scratch/"mnq-trade-memory-panel/bars.csv"
        assert hashlib.sha256(path.read_bytes()).hexdigest()=="d7b50850d843bae7e4360ce271bc2e12abbec85afa29269fb2acdebb676a6fac"
        frame=regular_hours(pd.read_csv(path),"2026-10-26","2026-11-02")
        assert frame.groupby(frame.index.strftime("%Y-%m-%d")).size().to_dict()==dict.fromkeys(
            ["2026-10-26","2026-10-27","2026-10-28","2026-10-29","2026-11-02"],390)
        return {"replication5":frame}
    src=get_panels(scratch)
    return {"earlier20":src["discovery"],"november14":pd.concat([src["november-extension"],src["november"]])}


def run(frames,out,encoder=None):
    verify_brain()
    out.mkdir(exist_ok=False,parents=True)
    summary={}
    traces=[]
    ledgers=[]
    daily=[]
    for name,bars in frames.items():
        group={}
        for day,b in bars.groupby(bars.index.date):
            a=activations(b,"reservoir")
            f=circuit(b,a)
            signals={"original":a.reservoir,"momentum":a.trend,"unloaded":f.unloaded,"loaded":f.loaded}
            if encoder is not None:
                extra,scores=encoder(b,a,f)
                f=f.join(extra)
                signals.update(scores)
            traces.append(f.assign(original=a.reservoir,scale=a.scale,signed_release=a.signed_release,close=b.close,panel=name))
            for model,score in signals.items():
                t,m=replay(b,score,cost=6.)
                group.setdefault(model,[]).append(t)
                if len(t):
                    ledgers.append(t.assign(panel=name,model=model))
                assert np.isclose(t.net_usd.sum(),m.iloc[-1])
                daily.append(dict(panel=name,date=str(day),model=model,net=m.iloc[-1],trades=len(t)))
        panel={}
        for model,parts in group.items():
            nonempty=[t for t in parts if len(t)]
            t=pd.concat(nonempty,ignore_index=True) if nonempty else parts[0]
            r=bounds(bars,t)
            pnl=t.net_usd.to_numpy(dtype=float)
            days=pd.Series([s["net"] for s in daily if s["model"]==model and s["panel"]==name])
            base=pd.Series([s["net"] for s in daily if s["model"]=="original" and s["panel"]==name])
            panel[model]=dict(**r,trades=len(t),expectancy=float(pnl.mean()) if len(t) else None,
                              net_9=float(pnl.sum()-3*len(t)),without_best_day=float(days.sum()-days.max()),
                              profitable_sessions=int((days>0).sum()),vs_cash=paired(days,0),vs_original=paired(days,base))
        summary[name]=panel
    (out/"scorecard.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n")
    pd.concat(traces).to_csv(out/"traces.csv.gz",compression={"method":"gzip","mtime":0})
    pd.concat(ledgers,ignore_index=True).to_csv(out/"trades.csv")
    pd.DataFrame(daily).to_csv(out/"daily.csv",index=False)
    return summary


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("scratch",type=Path);p.add_argument("output",type=Path)
    p.add_argument("--track",choices=["discovery","replication"],default="discovery")
    args=p.parse_args()
    run(panels(args.scratch,args.track),args.output)
