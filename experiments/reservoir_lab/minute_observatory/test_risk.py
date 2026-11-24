"""A wide held candle admits different high/low orders even with known closes."""
import pandas as pd
import pytest

from risk import bounds


@pytest.mark.parametrize("side",["long","short"])
def test_unknown_bar_order(side):
    idx=pd.date_range("2026-11-05 10:00",periods=2,freq="min",tz="America/New_York")
    b=pd.DataFrame(dict(open=[100.,100.],high=[110.,100.],low=[90.,100.],close=[100.,100.]),index=idx)
    t=pd.DataFrame([dict(entry_time=idx[0],exit_time=idx[1],entry=100.,side=side,net_usd=-6.)])
    # The marked path starts at zero, reserves $3 while open and pays $6 when closed.
    assert bounds(b,t)==dict(net=-6.,close_dd=6.,intraminute_min_dd=23.,intraminute_max_dd=40.)
