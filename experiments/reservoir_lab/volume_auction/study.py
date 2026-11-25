"""Score full policies and their ablations, using only closed-bar features."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
LAB=HERE.parent
sys.path.insert(0,str(LAB/"capacitor_bridge"))
from replay_lab import panels, verify_brain, activations, bounds, replay, paired
from simulator import simulate
from network import features,Readout
from impulse import encode
from timing import timed

def run(frames,out,redesign=None):
    verify_brain()
    out.mkdir(parents=True,exist_ok=False)
    scores={};ledgers=[];days=[];traces=[]
    for panel,frame in frames.items():
        all_trades={};daily={}
        for date,b in frame.groupby(frame.index.date):
            a=activations(b,"reservoir")
            signals={"original":(a.reservoir,None),"momentum":(a.trend,None)}
            layers={}
            for mode in ("volume","equal_volume","neutral"):
                layers[mode]=features(b,mode)
                signals[mode]=(layers[mode].score,Readout())
            trace=layers["volume"].join(layers["equal_volume"].score.rename("equal_score"))
            if redesign:
                extra,heads=redesign(b,a,layers)
                trace=trace.join(extra)
                signals.update(heads)
            launch=encode(b)
            for name in ("weighted","equal_mass","v08_sym","v08_long"):
                signals["pulse_"+name]=(launch[name],"timed")
            trace=trace.join(launch.add_prefix("pulse_"))
            traces.append(trace.assign(original=a.reservoir,panel=panel))
            for m,(s,head) in signals.items():
                if head=="timed":
                    t,marks=timed(b,s)
                elif head is None:
                    t,marks=replay(b,s,cost=6.)
                else:
                    t,marks,_=simulate(b,s,s,-s,policy=head)
                assert marks.iat[-1]==t.net_usd.sum()
                daily.setdefault(m,[]).append(marks.iat[-1])
                days.append(dict(panel=panel,date=str(date),model=m,trades=len(t),net=marks.iat[-1]))
                all_trades.setdefault(m,[]).append(t)
                if len(t):ledgers.append(t.assign(panel=panel,model=m))
        scores[panel]={}
        for m,parts in all_trades.items():
            t=pd.concat([t for t in parts if len(t)],ignore_index=True) if any(len(t) for t in parts) else parts[0]
            d=np.array(daily[m]); z=bounds(frame,t); n=len(t)
            scores[panel][m]=dict(**z,trades=n,gross=float(t.gross_usd.sum()),cost=6*n,
                expectancy=z["net"]/n if n else None,net_at_9=z["net"]-3*n,
                without_best_day=float(d.sum()-d.max()),profitable_days=int((d>0).sum()),
                active_days=int(t.entry_time.map(lambda x:x.date()).nunique()) if n else 0,
                vs_original=paired(d,np.array(daily["original"])),vs_equal=paired(d,np.array(daily["pulse_equal_mass" if m.startswith("pulse_") else "cascade_equal_volume" if m.startswith("cascade_") else "equal_volume"])),
                vs_cash=paired(d,0))
    (out/"summary.json").write_text(json.dumps(scores,indent=2,allow_nan=False)+"\n")
    pd.concat(ledgers).to_csv(out/"trades.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    pd.concat(traces).to_csv(out/"activations.csv.gz",compression={"method":"gzip","mtime":0})
    pd.DataFrame(days).to_csv(out/"daily.csv",index=False)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("scratch",type=Path);p.add_argument("out",type=Path)
    p.add_argument("--track",choices=["discovery","replication"],default="discovery")
    args=p.parse_args();run(panels(args.scratch,args.track),args.out)
