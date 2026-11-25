"""Compare first-observed bars/calls with the after-close frozen original."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pandas as pd

from replay_lab import LAB
sys.path.insert(0,str(LAB/"minute_observatory"))
from observer import FIELDS, NY, observe


def reconcile(raw,journal):
    item,=json.loads(raw.read_bytes())["chart"]["result"]
    final=pd.DataFrame(item["indicators"]["quote"][0],index=pd.to_datetime(item["timestamp"],unit="s",utc=True).tz_convert(NY))[FIELDS]
    with sqlite3.connect(f"file:{journal}?mode=ro",uri=True) as c:
        args=("Yahoo · delayed","MNQZ26","2026-11-24")
        cond=" WHERE feed=? AND contract=? AND substr(ts,1,10)=?"
        rows=c.execute("SELECT ts,values_json FROM bars"+cond+" ORDER BY ts",args).fetchall()
        calls=c.execute("SELECT ts,forecast,decision,side,computed FROM calls"+cond+" ORDER BY ts",args).fetchall()
        anomalies=c.execute("SELECT count(*) FROM exceptions"+cond,args).fetchone()[0]
    b=pd.DataFrame([json.loads(v) for _,v in rows],columns=FIELDS,
                   index=pd.to_datetime([s for s,_ in rows],utc=True).tz_convert(NY))
    live={r["bar"]:r for r in observe(b)}
    end={r["bar"]:r for r in observe(final)}
    revised=(b!=final.loc[b.index]).any(axis=1)
    lags=[];changed_forecasts=changed_decisions=0
    for ts,fc,decision,side,computed in calls:
        prior=live[ts]; close=end[ts]
        assert (fc,decision,side)==(prior["forecast"],prior["decision"],prior["side"])
        if fc is not None:
            if not np.isclose(fc,close["forecast"],rtol=0,atol=1e-9): changed_forecasts+=1
            lags.append((pd.Timestamp(computed)-pd.Timestamp(prior["decision_at"])).total_seconds())
        changed_decisions+=int((close["decision"],close["side"])!=(decision,side))
    aligned=final.loc[b.index]
    conditional={}
    for label,cols in [("first_seen",[]),("prices_only",FIELDS[:4]),("volume_only",["volume"]),("all",FIELDS)]:
        tape=b.copy()
        if cols:
            tape.loc[:,cols]=aligned[cols]
        path=observe(tape)
        mismatches=[r for r in path if r["decision"]!=end[r["bar"]]["decision"]]
        delta=sum((r["decision"],r["side"])!=(end[r["bar"]]["decision"],end[r["bar"]]["side"]) for r in path)
        conditional[label]=dict(prefix_mark=path[-1]["equity"],different_close_actions=len(mismatches),
                                different_action_or_position=delta,first_different_close_action=mismatches[0]["decision_at"] if mismatches else None)
    flags=(b.volume==0)&(b.high>b.low)
    details=[dict(bar=t.isoformat(),first_volume=float(b.volume.loc[t]),final_volume=float(aligned.volume.loc[t]),
                  first_range=float(b.high.loc[t]-b.low.loc[t]),changed_fields=[col for col in FIELDS if b.loc[t,col]!=aligned.loc[t,col]]) for t in b.index[revised]]
    return dict(revision_attribution=conditional,revisions=details,
                moving_zero_volume_first=int(flags.sum()),flagged_and_revised=int((flags&revised).sum()),
                first_seen_bars=len(b),after_close_bars=len(final),last_seen_bar=str(b.index[-1]),
                saved_calls=len(calls),eligible_forecasts=len(lags),revised_final_bars=int(revised.sum()),
                vendor_exceptions=anomalies,changed_forecast_magnitudes=changed_forecasts,
                changed_decision_or_position=changed_decisions,median_decision_lag_seconds=float(np.median(lags)),
                within_nine_seconds=sum(x<=9 for x in lags),common_prefix_equity_first_seen=list(live.values())[-1]["equity"],
                common_prefix_equity_after_close=end[b.index[-1].isoformat()]["equity"])


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for k in ("raw","journal","out"):p.add_argument(k,type=Path)
    a=p.parse_args()
    a.out.write_text(json.dumps(reconcile(a.raw,a.journal),indent=2)+"\n")
