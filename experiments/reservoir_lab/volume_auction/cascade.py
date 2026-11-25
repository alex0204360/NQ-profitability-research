"""Static counterfactual propagation over the current inventory, never future bars."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from network import W

C=json.loads(Path(__file__).with_name("cascade_weights.json").read_text())


def propagate(price,previous,scale,impulse,mass,used,lower,span):
    side=float(np.sign(impulse))
    distance=abs(price-previous)
    stop=max(W["tick"],distance)
    seed=max(0.,abs(impulse)-max(0.,side*(price-previous)))/scale
    def reachable(x):
        u=(price+side*scale*x-lower)/span
        fraction=(u if side>0 else 1-u)-W["adverse_span"]
        leg=1 if side>0 else 0
        return float(mass[:,leg] @ np.maximum(0.,np.clip(fraction,0,1)-used[:,leg]))
    critical=reachable(1.) if seed else 0.
    x=seed
    for _ in range(C["layers"] if seed and critical>=C["critical_range_mass"] else 0):
        x=(seed**2+reachable(x))**C["impact_exponent"]
    reward=scale*x
    event=side if seed and critical>=C["critical_range_mass"] and reward>stop+W["entry_cost_points"] else 0.
    return seed,critical,reward,price+side*reward,price-side*stop,event


class Barrier:
    def __init__(self,trace):
        self.frame=trace

    def close_scores(self,i,close,raw,position,exited,contiguous,long_hold,short_hold):
        event=self.frame.event.iat[i]
        remaining=np.nan
        if position:
            t=self.frame.loc[position["signal_time"]]
            side=position["side"]
            remaining=min(side*(t.target-close),side*(close-t.invalidation))
        # The execution adapter expects a signed number above its 1.5-point entry hurdle.
        return event*self.frame.reward.iat[i],remaining


def make(b,a,layers):
    from network import features
    extra=[]
    heads={}
    for mode in layers:
        t=features(b,mode,field=propagate)
        last=t.event.where(t.event!=0).ffill().fillna(0.)
        last=last.where(t.age>=W["cohorts"])
        heads["cascade_"+mode]=(last,Barrier(t))
        extra.append(t[["seed","critical","reward","target","invalidation","event"]].add_prefix(mode+"_"))
    return pd.concat(extra,axis=1),heads
