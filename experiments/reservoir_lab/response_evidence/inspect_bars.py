"""Inspect one dated session using only a prefix of closed UTC minute bars."""
import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[1]/"path_order"), str(HERE.parent/"adverse_impact")]
from brain import activations
from agreement import Agreement
from auction import states
from exit_head import ExitHead, inputs
from restart import RestartHead


def read_day(path, date, through):
    df = pd.read_csv(path)
    key = "timestamp_utc" if "timestamp_utc" in df else "datetime"
    df.index = pd.DatetimeIndex(pd.to_datetime(df.pop(key), utc=True)).tz_convert("America/New_York")
    begin = pd.Timestamp(f"{date} 09:30",tz="America/New_York")
    end = pd.Timestamp(f"{date} {through}",tz=begin.tz)
    if end < begin or end.time()>pd.Timestamp("15:59").time():
        raise ValueError("through must be a regular-hours bar-start time")
    rows = df[(df.index>=begin)&(df.index<=end)]
    if "contract" in rows and rows.contract.nunique(dropna=False)!=1:
        raise ValueError("supply one dated contract")
    b = rows[["open","high","low","close","volume"]]
    if not b.index.equals(pd.date_range(begin,end,freq="min")):
        raise ValueError("expected every minute up to the last completed bar")
    if (not np.isfinite(b.to_numpy()).all() or (b.volume<0).any() or
        (b.high<b[["open","close"]].max(axis=1)).any() or (b.low>b[["open","close"]].min(axis=1)).any()):
        raise ValueError("invalid OHLCV")
    return b


def diagnostics(b, nq, side, entry):
    a = activations(b,"reservoir")
    raw = a.reservoir.iat[-1]
    out = {"bar_start_et":b.index[-1].isoformat(),"decision_at_et":(b.index[-1]+pd.Timedelta(minutes=1)).isoformat(),
           "forecast_pts":raw,"state":"warmup" if not np.isfinite(raw) else "ready"}
    if nq is not None:
        if not b.index.equals(nq.index):
            raise ValueError("peer must have identical closed bars")
        peer = activations(nq,"reservoir").reservoir
        out["nq_forecast_pts"] = peer.iat[-1]
        gate = Agreement(peer, True)
        position = {"side":side} if side else None
        common, hold = gate.close_scores(-1,0.,raw,position,None,True,raw,-raw)
        out["common_entry_score_pts"] = common
        out["common_hold_pts"] = hold
    if side:
        first = pd.Timestamp(f"{b.index[0].date()} {entry}",tz=b.index.tz)
        if first not in b.index:
            raise ValueError("entry must be within the closed bars")
        rows = inputs(b)
        for cls, key in ((ExitHead,"original_evidence"),(RestartHead,"restart_evidence")):
            h = cls(rows,True)
            for i in range(b.index.get_loc(first),len(b)):
                _, margin = h.close_scores(i,0.,a.reservoir.iat[i],{"side":side},None,True,0.,0.)
                if not np.isfinite(margin) or margin<=0:
                    break
            out[key]={"last_held_close":b.index[i].isoformat(),"evidence":h.activations[-1][2],
                      "hold_pts":float(margin) if np.isfinite(margin) else None}
    if b.index[-1].time()==pd.Timestamp("15:29").time():
        out["closing_scores_pts"]={k:float(v) for k,v in states(b) if np.isfinite(v)}
    return {k:None if isinstance(v,float) and not math.isfinite(v) else v for k,v in out.items()}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("mnq",type=Path); p.add_argument("date"); p.add_argument("through",help="last completed bar start in New York")
    p.add_argument("--nq",type=Path);p.add_argument("--side",choices=["long","short"]);p.add_argument("--entry")
    args=p.parse_args()
    if bool(args.side)!=bool(args.entry): p.error("supply side and entry together")
    if args.side and args.through>="15:55": p.error("the policy is flat from 15:55 ET")
    b=read_day(args.mnq,args.date,args.through)
    nq=read_day(args.nq,args.date,args.through) if args.nq else None
    print(json.dumps(diagnostics(b,nq,{"long":1,"short":-1}.get(args.side),args.entry),indent=2,allow_nan=False))
