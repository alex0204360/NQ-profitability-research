"""A rectified, displacement-limited RC load in physical price units."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

CFG=json.loads(Path(__file__).with_name("load_weights.json").read_text())


def circuit(bars, a):
    motion=np.asarray(CFG["oriented_motion"])
    polarity=np.asarray(CFG["cap_readout"])
    v=unloaded=prev=0.
    rows=[]
    for close, r in zip(bars.close,a.itertuples(),strict=True):
        if r.age==1:
            v=unloaded=0.
            prev=close
        available=np.maximum(0.,polarity*v)
        travel=np.maximum(0.,motion @ [close,prev])
        delivered=np.minimum(available,CFG["load"]*travel)
        injection=CFG["current_weight"]*r.scale*r.signed_release
        old=v
        v=CFG["leak"]*(polarity @ (available-delivered))+injection
        unloaded=CFG["leak"]*unloaded+injection
        rows.append((old,injection,polarity @ delivered,v,unloaded))
        prev=close
    f=pd.DataFrame(rows,index=bars.index,columns=["previous_voltage","injection","delivered","loaded","unloaded"])
    f.loc[a.reservoir.isna(),["loaded","unloaded"]]=np.nan
    return f
