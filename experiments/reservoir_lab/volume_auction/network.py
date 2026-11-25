"""Two-sided cohort memory and a displacement readout, programmed without fitting."""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

W=json.loads(Path(__file__).with_name("weights.json").read_text())


def features(bars, mode="volume"):
    if mode not in ("volume","equal_volume","neutral"):
        raise ValueError("unknown cohort allocation")
    n=W["cohorts"]
    signed=np.array(W["flow_readout"])
    location=np.array(W["location"])
    sides=np.array(W["orient"])
    # Rows are age-limited cohorts; columns are excess buyers and excess sellers.
    mass=np.zeros((n,2))
    used=np.zeros_like(mass)
    lower=np.zeros(n); span=np.ones(n)
    prior_time=None
    age=0
    rows=[]
    for bar in bars.itertuples():
        width=bar.high-bar.low
        suspect=bar.volume==0 and width>0
        v=1. if mode=="equal_volume" else float(bar.volume)
        if prior_time is None or bar.Index-prior_time!=pd.Timedelta(minutes=1) or suspect or age==0:
            age=0
            mass.fill(0);used.fill(0)
            volume_mean=max(v,1.);range_mean=max(width,W["tick"])
            previous=bar.close
            voltage=0.
        prior_time=bar.Index
        if suspect:
            rows.append((0,True,*([math.nan]*9)))
            continue
        scale=max(range_mean,W["tick"])
        q=v/max(volume_mean,1.)
        retain=math.exp(-math.log(2)*q/W["baseline_volume_half_life"])
        mass*=retain
        # Long cost p is under water if close < p-span. Short is the reflection.
        u=(bar.close-lower)/span
        fraction=np.clip(np.column_stack((1-u-W["adverse_span"],u-W["adverse_span"])),0,1)
        fresh=np.maximum(fraction-used,0.)
        flow=(mass*fresh).sum(axis=0)
        np.maximum(used,fraction,out=used)
        imbalance=float(signed@flow)
        injection=scale*math.copysign(abs(imbalance)**W["impact_exponent"],imbalance)
        sign=np.sign(voltage)
        paid=min(abs(voltage),max(0.,sign*(bar.close-previous)))
        voltage=retain*(voltage-sign*paid)+injection
        slot=age%n
        loc=float(location@[bar.close,bar.high,bar.low])/max(width,W["tick"])
        mass[slot]=q*(np.full(2,.5) if mode=="neutral" else np.maximum(0.,sides*loc))
        used[slot]=0
        lower[slot]=bar.low if width else bar.close-W["tick"]/2
        span[slot]=max(width,W["tick"])
        age+=1
        rows.append((age,False,q,loc,flow[0],flow[1],injection,paid,voltage,scale,voltage if age>=n else math.nan))
        d=W["prior_decay"]
        volume_mean=d*volume_mean+(1-d)*v
        range_mean=d*range_mean+(1-d)*width
        previous=bar.close
    return pd.DataFrame(rows,index=bars.index,columns=["age","suspect","normalized_volume","close_location",
        "forced_sell","forced_buy","impulse_pts","spent_pts","voltage","scale","score"])


class Readout:
    def close_scores(self,i,close,raw,position,exited,contiguous,long_hold,short_hold):
        entry=raw if abs(raw)>W["entry_cost_points"] else 0.
        return entry,abs(raw)-W["exit_floor_points"]
