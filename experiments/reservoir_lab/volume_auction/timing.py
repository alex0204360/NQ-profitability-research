"""A fixed-horizon head using next observed opens for fills, with cutoff and gaps."""
import numpy as np
import pandas as pd
from impulse import C


def timed(b,score):
    records=[]
    previous=None
    position=None
    pending=None
    marked=[]
    realized=0.
    minute=pd.Timedelta(minutes=1)
    cutoff=pd.Timestamp("15:55").time()
    for bar,s in zip(b.itertuples(),score,strict=True):
        ts=bar.Index
        gap=previous is not None and ts-previous!=minute
        if gap or ts.time()>=cutoff:pending=None
        if position:
            signal,entry,price,side=position
            reason=None
            if gap:reason="gap"
            elif ts.time()>=cutoff:reason="cutoff"
            elif ts>=entry+C["holding_bars"]*minute:reason="horizon"
            elif pending=="quality":reason="quality"
            if reason:
                gross=2*side*(bar.open-price)
                records.append((signal,entry,ts,"long" if side==1 else "short",price,bar.open,gross,gross-6,reason))
                realized+=gross-6
                position=None
        elif pending is not None:
            signal,side=pending
            position=(signal,ts,bar.open,side)
        pending=None
        if ts.time()<cutoff and position is None and abs(s)>C["cost_points"]:
            pending=(ts,1 if s>0 else -1)
        if position is not None and not np.isfinite(s):pending="quality"
        marked.append(realized+(position[3]*(bar.close-position[2])*2-3 if position else 0))
        previous=ts
    if position:raise ValueError("incomplete daytime session")
    return (pd.DataFrame(records,columns=["signal_time","entry_time","exit_time","side","entry","exit","gross_usd","net_usd","reason"]),
            pd.Series(marked,index=b.index))
