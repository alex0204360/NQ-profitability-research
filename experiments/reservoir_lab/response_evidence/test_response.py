from itertools import product

import numpy as np
import pandas as pd
from inspect_bars import activations, diagnostics
from exit_head import ExitHead, inputs
from restart import RestartHead
from auction import states, strategies


def session():
    index = pd.date_range("2026-02-02 09:30",periods=390,freq="min",tz="America/New_York")
    x = 24000+np.arange(390)*.25
    return pd.DataFrame(dict(open=x,high=x+.5,low=x-.25,close=x+.25,volume=10),index=index)


def test_null_mixture_is_fair_and_first_spike_cannot_stop():
    capitals = []
    for path in product([-1,1],repeat=7):
        h=ExitHead([(v,1.,1.) for v in path],True)
        for i in range(len(path)):
            h.close_scores(i,0,1.,{"side":1},None,True,0,0)
        assert h.activations[0][2]<8.
        capitals.append(h.activations[-1][2])
    np.testing.assert_allclose(np.mean(capitals),1.)


def test_restart_recovers_sensitivity_after_favorable_run():
    rows=[(v,1.,1.) for v in [1]*40+[-1]*7]
    heads=[cls(rows,False) for cls in (ExitHead,RestartHead)]
    for i in range(len(rows)):
        for h in heads:
            h.close_scores(i,0,1.,{"side":1},None,True,0,0)
    assert heads[0].activations[-1][2]<1<8<heads[1].activations[-1][2]


def test_closed_prefix_and_mirrored_auction():
    b=session()
    prefix=b.iloc[:360]
    assert states(prefix)==states(b)
    assert states(prefix.iloc[:-1])==[]
    assert inputs(prefix)==inputs(b)[:len(prefix)]
    assert diagnostics(prefix,prefix,None,None)["closing_scores_pts"]["auction"]>0
    m=b.copy()
    m["open"],m["close"],m["low"],m["high"]=[48000-b[k] for k in ("open","close","high","low")]
    assert dict(states(b))["auction"]==-dict(states(m))["auction"]
    assert strategies(b)["auction"].iloc[0].exit_time.strftime("%H:%M")=="15:55"
    assert not states(b.drop(b.index[80]))
