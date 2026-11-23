"""Outcome-only analysis of completed replay files; never imported by the trading circuit."""
import argparse
import json
from pathlib import Path

import pandas as pd

from study import CORE, get_panels, FOCUS
import sys
sys.path.insert(0,str(CORE))
from evaluate import paired
from circuit import CFG


def evaluate_outputs(scratch,out):
    daily=pd.read_csv(out/"daily.csv").pivot(index="date",columns="mode",values="net")
    cohorts={"earlier20": daily.index < "2026-11", "all_november": daily.index >= "2026-11",
             "november_other13": (daily.index >= "2026-11") & (daily.index != FOCUS)}
    result={"incremental_volume_usd_per_day":{}, "hold_labels":{}}
    for panel, mask in cohorts.items():
        block=daily.loc[mask]
        result["incremental_volume_usd_per_day"][panel]={s:paired(block[s+"_volume"],block[s+"_price"])
                                                        for s in ["fixed","full"]}
    archive=pd.concat(get_panels(scratch).values())
    trace=pd.read_csv(out/"neurons.csv.gz", index_col=0)
    trace.index=pd.to_datetime(trace.index,utc=True)
    trades=pd.read_csv(out/"original-trades.csv")
    pairs=[]
    for t in trades.itertuples():
        start,end=(pd.Timestamp(stamp).tz_convert(archive.index.tz) for stamp in [t.entry_time,t.exit_time])
        side=1 if t.side=="long" else -1
        path=archive.loc[start:end]
        for ts in path.index[:-1]:
            next_open=ts+pd.Timedelta(minutes=1)
            # Include only decisions with a positive, fully observed remaining interval.
            due=min(next_open+pd.Timedelta(minutes=CFG["horizon_minutes"]),end)
            minutes=int((due-ts)/pd.Timedelta(minutes=1))
            if due<=next_open or len(path.loc[ts:due]) != minutes+1:
                continue
            realized=side*(path.at[due,"open"]-path.at[next_open,"open"])
            row={"panel":"earlier20" if ts.month<11 else "all_november","realized":realized}
            for ctrl in ["volume","price"]:
                row[ctrl]=trace.at[ts,ctrl+"_"+t.side+"_hold"]
            pairs.append(row)
    labels=pd.DataFrame(pairs)
    for panel,block in labels.groupby("panel"):
        scores={}
        for ctrl in ["volume","price"]:
            for sign,mask in [("exit",block[ctrl]<=0),("hold",block[ctrl]>0)]:
                g=block[mask]
                scores[ctrl+"_"+sign]={"observations":len(g),"mean_score":float(g[ctrl].mean()),
                                      "mean_realized_signed_points":float(g.realized.mean())}
        result["hold_labels"][panel]=scores
    (out/"diagnostics.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("scratch",type=Path)
    p.add_argument("out",type=Path)
    args=p.parse_args()
    evaluate_outputs(args.scratch,args.out)
