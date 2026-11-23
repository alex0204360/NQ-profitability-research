import numpy as np
import pandas as pd
from .circuit import directional_state


def test_requires_attempt_subsequent_break_and_no_reuse():
    t=pd.date_range("2026-11-05 09:45",periods=7,freq="min",tz="America/New_York")
    b=pd.DataFrame({"close":[100.,99.,95.,97.5,96.,94.,93.]},index=t)
    a=pd.DataFrame({"scale":1., "effort":0., "reservoir":2.},index=t)
    h=directional_state(b,a,1)
    assert h.armed.tolist()==[False,False,False,True,True,False,False]
    np.testing.assert_allclose(h.failure_points, [0,0,0,0,0,3.5,0])
    assert h.hold.iloc[5]<0 and h.hold.iloc[6]>0
    pd.testing.assert_frame_equal(h.iloc[:5],directional_state(b.iloc[:5],a.iloc[:5],1))
    mirror=directional_state(200-b,a.assign(reservoir=-2),-1)
    np.testing.assert_allclose(h.hold,mirror.hold)
    b.iloc[4,0]=99.
    assert (directional_state(b,a,1).failure_points == 0).all()
