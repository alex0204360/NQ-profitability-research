"""Sample a shock, observe a recovery attempt, debit only a subsequent failed retest."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

CFG=json.loads(Path(__file__).with_name("weights.json").read_text())


def directional_state(bars, activation, side, with_volume=True):
    if side not in (-1,1) or not bars.index.equals(activation.index):
        raise ValueError("expected aligned position-side inputs")
    update=np.asarray(CFG["usual_update"])
    detect=np.asarray(CFG["surprise_rows"])
    recovery=np.asarray(CFG["recovery_rows"])
    break_row=np.asarray(CFG["break_row"])
    readout=np.asarray(CFG["hold_readout"])
    rows=[]
    previous_time=None
    for ts,close,scale,effort,raw in zip(bars.index,bars.close,activation.scale,
                                         activation.effort,activation.reservoir,strict=True):
        x=side*close
        if previous_time is None or ts-previous_time!=pd.Timedelta(minutes=1):
            previous=x
            usual=impact=low=high=peak=np.nan
            armed=False
        adverse=max(previous-x,0.)/scale
        volume=CFG["volume_base"]**effort if with_volume else CFG["price_control_volume"]
        shock=False
        if adverse>0:
            if np.isfinite(usual):
                shock=bool((detect @ [adverse,usual,volume*impact]>0).all())
                usual=update @ [usual,adverse]
                impact=update @ [impact,adverse/volume]
            else:
                usual,impact=adverse,adverse/volume
        pulse=0.
        if np.isfinite(low):
            displacement=x-low
            span=high-low
            half,whole=recovery @ [displacement,span] >= 0
            if whole:
                low=high=peak=np.nan
                armed=False
            elif armed and break_row @ [displacement,span] > 0:
                pulse=peak-x
                low=high=peak=np.nan
                armed=False
            elif half:
                armed=True
                peak=max(peak,x)
        if shock and not armed and pulse==0 and (not np.isfinite(low) or x<low):
            low,high,peak=x,previous,x
        hold=readout @ [side*raw,pulse]
        rows.append((hold,shock,side*low,side*high,side*peak,armed,pulse))
        previous,previous_time=x,ts
    return pd.DataFrame(rows,index=bars.index,columns=[
        "hold","new_shock","shock_end","shock_start","recovery_peak","armed","failure_points"])
