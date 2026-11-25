"""Parallel long/short launch, collision, overhead inventory and wick neurons."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

C=json.loads(Path(__file__).with_name("impulse_weights.json").read_text())


def encode(b):
    names=["weighted","equal_mass","v08_sym","v08_long"]
    out=pd.DataFrame(np.nan,index=b.index,columns=[*names,"range","velocity","collision","overhead_long","overhead_short"])
    bad=(b.volume==0)&(b.high>b.low)
    breaks=b.index.to_series().diff().ne(pd.Timedelta(minutes=1)) | bad | bad.shift(fill_value=False)
    for _,g in b.groupby(breaks.cumsum()):
        if len(g)<17:continue
        h,l,c,v=[g[k].to_numpy(float) for k in ["high","low","close","volume"]]
        n=C["background_bars"]
        j=np.arange(n+2,len(g))
        ctx=j[:,None]+np.arange(-n-1,-1)
        anchor=c[j-2];typ=(h+l+c)/3
        scale=(h-l)[ctx].mean(axis=1)
        d1=anchor*-1+c[j-1];d2=c[j]-c[j-1]
        for name in names:
            weighted=name=="weighted"
            base=name.startswith("v08")
            mass=v[ctx] if weighted else np.ones_like(v[ctx])
            weights=np.divide(v[j],v[j]+v[j-1],out=np.full(len(j),.5),where=(v[j]+v[j-1])>0) if weighted else np.full(len(j),.5)
            vel=2*((1-weights)*d1+weights*d2)
            collision=np.sqrt(weights*(1-weights))*np.abs(d1-d2) if not base else np.zeros(len(j))
            outputs=[]
            for side in (1,-1):
                # v08 uses the pre-launch close and the previous 14 old closes
                # indexed from j-3 backwards to j-16.
                rel=c[ctx-1]-anchor[:,None] if base else typ[ctx]-anchor[:,None]
                overhead=np.sum(mass*np.maximum(0.,side*rel),axis=1)/np.maximum(1,mass.sum(axis=1))
                wick=h[j]-c[j] if side==1 else c[j]-l[j]
                drift=C["drift_gain"]*np.maximum(0.,side*(anchor-c[j-16]))
                surplus=np.array(C["surplus"])@np.stack((side*vel,collision,wick,overhead,drift,scale))
                score=np.maximum(0.,np.minimum.reduce([surplus,scale,2*side*d1,2*side*d2]))
                outputs.append(score)
                if weighted:
                    out.loc[g.index[j],"overhead_long" if side==1 else "overhead_short"]=overhead
            out.loc[g.index[j],name]=outputs[0] if name=="v08_long" else outputs[0]-outputs[1]
            if weighted:
                out.loc[g.index[j],["range","velocity","collision"]]=np.column_stack((scale,vel,collision))
    return out


class Pulse:
    def __init__(self,score):
        self.score=score

    def close_scores(self,i,close,raw,position,exited,contiguous,long_hold,short_hold):
        score=self.score.iat[i]
        entry=score if abs(score)>C["cost_points"] else 0.
        hold=1.
        if position:
            elapsed=(self.score.index[i]-position["entry_time"])/pd.Timedelta(minutes=1)
            hold=0. if not np.isfinite(score) or elapsed>=C["holding_bars"]-1 else 1.
        return entry,hold
