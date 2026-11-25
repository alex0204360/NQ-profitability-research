"""A delayed feedback circuit. Each phase sees only a previously matured move."""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

CFG=json.loads(Path(__file__).with_name("bridge_weights.json").read_text())
SPAN=1+CFG["horizon"]
PRIOR=np.array(CFG["prior"])
SCALE=math.sqrt(CFG["horizon"]*math.pi/8)*math.sqrt(3)/math.pi


def class_probs(centers,scale):
    arg=(np.array([-CFG["cost_points"],CFG["cost_points"]])-centers[:,None])/(SCALE*scale)
    cdf=np.exp(-np.logaddexp(0.,-arg))
    probs=np.stack((cdf[:,0],cdf[:,1]-cdf[:,0],1-cdf[:,1]),axis=1)
    return (1-CFG["contamination"])*probs+CFG["contamination"]/3


def apply(b,a,f):
    logw=np.tile(np.log(PRIOR),(SPAN,1))
    pending={}
    weights=[]
    score=[]
    records=[]
    segment=-1
    for i,(bar,raw,loaded,scale,age) in enumerate(zip(b.itertuples(),a.reservoir,f.loaded,a.scale,a.age,strict=True)):
        if age==1:
            segment+=1
            pending.clear()
            logw[:]=np.log(PRIOR)
        phase=(age-1)%SPAN
        # On bar i, open[i] and open[i-4] are observable; the origin is i-5.
        if phase in pending:
            j,branch_p,mix,uniform=pending.pop(phase)
            assert i-j==SPAN
            movement=bar.open-b.open.iat[j+1]
            target=0 if movement < -CFG["cost_points"] else 2 if movement > CFG["cost_points"] else 1
            observation=branch_p[:,target]
            records.append((b.index[j],bar.Index,segment,phase,target,movement,
                            *observation,mix[target],uniform[target],*mix,*uniform,
                            *branch_p.flatten()))
            logw[phase]+=CFG["feedback_gain"]*np.log(observation)
            logw[phase]-=np.logaddexp.reduce(logw[phase])
        w=np.exp(logw[phase])
        weights.append(w.copy())
        centers=np.array([raw,loaded,0.])
        score.append(w @ centers)
        if not np.isfinite(raw) or bar.Index.hour*60+bar.Index.minute+SPAN>CFG["end_minute"]:
            continue
        branch_p=class_probs(centers,scale)
        pending[phase]=(i,branch_p,w @ branch_p,PRIOR @ branch_p)
    d=pd.DataFrame(weights,index=b.index,columns=["w_original","w_loaded","w_zero"])
    d["bridge"]=score
    d["fixed_bridge"]=(a.reservoir+f.loaded)/3
    names=["origin","matures","segment","phase","target","move","p_original","p_loaded","p_zero","p_bridge","p_fixed",
           *[f"{m}_{k}" for m in ("bridge","fixed","original","loaded","zero") for k in range(3)]]
    return d,pd.DataFrame(records,columns=names)
