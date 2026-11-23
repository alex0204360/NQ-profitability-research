import numpy as np
import pandas as pd

from tick_exit.neuron import tick_exit
from return_to_anchor.model import anchor_state


def test_piecewise_transfer_and_flat_entry_invariance():
    raw = pd.Series([np.nan, 0, .125, .25, .375, .5, 1.5, 1.501, 20])
    edited = tick_exit(raw)
    np.testing.assert_allclose(edited, [np.nan,0,0,0,.25,.5,1.5,1.501,20])
    np.testing.assert_allclose(tick_exit(-raw), -edited)
    np.testing.assert_array_equal(raw.abs() > 1.5, edited.abs() > 1.5)


def test_retirement_rearm_reflection_and_prefix():
    raw = pd.Series([2.,.1,.01,2.,3.,-2.,np.nan,2.])
    close = pd.Series([100.,101.,102.,100.,104.,103.,101.,100.])
    scale = pd.Series([2.] * len(raw))
    a = anchor_state(raw,close,scale)
    assert list(a.retired) == [False,False,False,True,True,False,False,False]
    np.testing.assert_allclose(a.score,[2,.1,.01,0,0,-2,np.nan,2])
    mirror = anchor_state(-raw,200-close,scale)
    np.testing.assert_allclose(mirror.score,-a.score)
    pd.testing.assert_frame_equal(anchor_state(raw[:4],close[:4],scale[:4]), a.iloc[:4])
