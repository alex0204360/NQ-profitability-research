import numpy as np
import pandas as pd

from circuit import CFG, directional_state


def test_delay_recovery_and_volume_control():
    t = pd.date_range("2026-09-14 10:00", periods=6, freq="min", tz="America/New_York")
    b = pd.DataFrame({"close":[100,99,96,96,99,98]},index=t)
    a = pd.DataFrame({"scale":1., "effort":[0,0,1,0,0,0], "reservoir":4.},index=t)
    v = directional_state(b,a,1)
    p = directional_state(b,a,1,False)
    np.testing.assert_allclose(v.pending_shock[:3], [0,0,1])
    np.testing.assert_allclose(p.pending_shock[:3], [0,0,2])
    np.testing.assert_allclose(v.debt[:5], [0,0,0,1,0])
    np.testing.assert_allclose(p.debt[:5], [0,0,0,2,0])
    assert v.hold.iloc[2] > 0 and v.hold.iloc[3] < 0
    np.testing.assert_allclose(directional_state(b,a.assign(effort=0),1).hold,p.hold)
    np.testing.assert_allclose(directional_state(200-b,a.assign(reservoir=-4),-1).hold,v.hold)
    pd.testing.assert_frame_equal(v.iloc[:3],directional_state(b.iloc[:3],a.iloc[:3],1))
    pd.testing.assert_frame_equal(directional_state(b.drop(t[2]),a.drop(t[2]),1).iloc[2:],
                                  directional_state(b.iloc[3:],a.iloc[3:],1),check_freq=False)
    h=CFG["horizon_minutes"]
    np.testing.assert_allclose(CFG["hold_weights"],[1-CFG["reference_decay"]**h,
                              -sum(CFG["debt_weights"][0]**j for j in range(1,h+1))])
