import numpy as np
import pandas as pd

from routing import TradeMemory


def inputs():
    t=pd.date_range("2026-11-19 10:00",periods=6,freq="min",tz="America/New_York")
    a=pd.DataFrame({"motion":[0,0,1,0,1,0],"charge":[0,0,0,1,0,0],"scale":10.},index=t)
    return a, {1:np.array([False,True,False,False,False,False]),-1:np.zeros(6,bool)}


def test_new_deposit_only_supports_later_entry():
    a,shocks=inputs(); p=TradeMemory(a,shocks,False,True)
    close=lambda i,exit=None,raw=6.:p.close_scores(i,100.,raw,None,exit,True,1.,1.)[0]
    assert close(0)==6
    assert close(1,{"reason":"hold","side":"long"})==0.
    assert close(2)==0.  # movement without stock cannot re-use the old forecast
    assert close(3)==0.  # charge alone cannot provide direction
    assert close(4)==6.  # new release independently clears the hurdle
    assert close(5,raw=-8.)==-8.


def test_shock_at_entry_ineligible_but_later_retest_triggers():
    a,s=inputs()
    def run(entry):
        p=TradeMemory(a,s,True,False)
        values=[]
        for i,c in enumerate([100.,96.,98.,95.,95.,95.]):
            pos=None if i<entry else {"entry_time":a.index[entry],"side":1}
            values.append(p.close_scores(i,c,4.,pos,None,i>0,2.,2.)[1])
        return values
    assert run(0)[3]<0
    assert run(1)[3]>0
