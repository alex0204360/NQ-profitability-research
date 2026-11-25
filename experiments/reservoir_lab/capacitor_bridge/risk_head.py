"""Causal path-risk quantile neuron. Money and width have separate units."""
from collections import deque
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

CFG=json.loads(Path(__file__).with_name("risk_weights.json").read_text())
H=CFG["horizon"]
Q=CFG["coverage"]
INITIAL=CFG["quantile_z"]*math.sqrt(H*math.pi/8)


class RiskCapacitor:
    def __init__(self):
        self.log_scale=math.log(INITIAL)
        self.history=deque(maxlen=CFG["prior_window"])

    def feedback(self,origin,miss):
        self.log_scale+=CFG["log_gain"]*(float(miss)-(1-Q))

    def session(self,b,a):
        pending={}
        records=[]
        trace=[]
        for i,(bar,scale,age) in enumerate(zip(b.itertuples(),a.scale,a.age,strict=True)):
            if age==1:
                pending.clear()
            if i in pending:
                origin,old,physical,rolling=pending.pop(i)
                start=b.open.iat[origin+1]
                up=max(b.high.iloc[origin+1:i].max(),bar.open)-start
                down=start-min(b.low.iloc[origin+1:i].min(),bar.open)
                distance=max(up,down)
                records.append((b.index[origin],bar.Index,up,down,distance,old,physical,rolling))
                self.feedback(b.index[origin],distance>old)
                self.history.append(distance)
            band=scale*math.exp(self.log_scale)
            physical=scale*INITIAL
            empirical=(float(np.quantile(self.history,Q,method="higher"))
                       if len(self.history)==self.history.maxlen else physical)
            trace.append((band,physical,empirical,self.log_scale))
            if age>=32 and bar.Index.hour*60+bar.Index.minute+1+H<=955:
                pending[i+1+H]=(i,band,physical,empirical)
        values=pd.DataFrame(trace,index=b.index,columns=["band","physical","rolling","log_scale"])
        labels=pd.DataFrame(records,columns=["origin","matures","up","down","travel","band","physical","rolling"])
        return values,labels


class Reserve:
    def __init__(self):
        self.realized=0.
        self.peak=0.
        self.blocks=0

    def prepare(self,b,band):
        self.bars=b
        self.band=band.to_numpy()

    def close_scores(self,i,close,raw,position,exited,contiguous,long_hold,short_hold):
        if exited is not None:
            self.realized+=exited["net_usd"]
        marked=high=self.realized
        if position:
            side=position["side"]
            top=self.bars.high.iat[i] if side>0 else self.bars.low.iat[i]
            marked+=side*(close-position["entry"])*CFG["point_usd"]-CFG["cost_usd"]/2
            high+=side*(top-position["entry"])*CFG["point_usd"]-CFG["cost_usd"]/2
        self.peak=max(self.peak,high)
        room=CFG["budget_usd"]+marked-self.peak
        required=self.band[i]*CFG["point_usd"]+CFG["cost_usd"]
        if room<required:
            self.blocks+=1
            return 0.,0.
        return raw,abs(raw)
