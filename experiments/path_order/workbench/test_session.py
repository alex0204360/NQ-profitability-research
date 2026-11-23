from datetime import date, datetime
import numpy as np
import pandas as pd
import pytest
from paper_day import completed, NY, prepare
from session import simulate_day, verify_brain


def test_first_loss_lock_and_next_open_slippage():
    stamps = pd.date_range("2026-11-20 15:48", periods=10, freq="min", tz=NY)
    bars = pd.DataFrame({"open":[1000,1000,999,700,690,800,900,900,900,900],
                         "close":[1000,999,747,700,690,800,900,900,900,900]},index=stamps)
    score = pd.Series([2,2,2,-2,-2,2,2,2,2,2],index=stamps)
    a,_,g,m,trigger=simulate_day(bars,score)
    assert trigger==stamps[2] and g.iloc[0].exit_time==stamps[3]
    assert g.iloc[0].reason=="daily loss" and m.iloc[-1]==-606 and len(g)==1 and len(a)>1
    # Future prices can change the exit fill, never the first lock time.
    bars.loc[stamps[3]:,["open","close"]]=1200.
    assert simulate_day(bars,score)[-1]==trigger


def test_no_trigger_and_zero_trades():
    t = pd.date_range("2026-11-20 10:00", periods=5, freq="min", tz=NY)
    bars=pd.DataFrame({"open":100,"close":100},index=t)
    a,e,g,m,first=simulate_day(bars,pd.Series(0.,index=t))
    pd.testing.assert_frame_equal(a,g)
    pd.testing.assert_series_equal(e,m)
    assert first is None


def test_completed_boundary_and_contract():
    day=date(2026,11,23)
    with pytest.raises(ValueError):
        completed(day,datetime(2026,11,23,15,59,tzinfo=NY))
    completed(day,datetime(2026,11,23,16,tzinfo=NY))
    stamps=pd.date_range("2026-11-23 09:31",periods=390,freq="min",tz=NY).tz_convert("UTC")
    raw=pd.DataFrame(dict(timestamp_utc=stamps,open=100.,high=101.,low=99.,close=100.,volume=20,contract="MNQZ26"))
    assert len(prepare(raw,day,"MNQZ26","end"))==390
    with pytest.raises(ValueError):
        prepare(raw.iloc[::5],day,"MNQZ26","end")
    with pytest.raises(ValueError):
        prepare(raw,day,"MNQH27","end")
    verify_brain()
