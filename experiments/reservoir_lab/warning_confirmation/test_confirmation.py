"""Check warning time, price symmetry, equality and forced exits with synthetic bars."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT/"experiments/reservoir_lab/adverse_impact")]
from simulator import simulate
from experiments.reservoir_lab.warning_confirmation.circuit import WarningMemory


def trial(side, next_step, mode="confirm", break_raw=False, gap=False):
    idx = pd.date_range("2026-09-14 15:46", periods=10, freq="min", tz="America/New_York")
    directional = [0,0,-7,-3,-9,-9+next_step,-6,-5,-4,-3]
    close = pd.Series([100+side*x for x in directional], index=idx)
    bars = pd.DataFrame({"close":close, "open":close.shift(fill_value=100)},index=idx)
    raw = pd.Series(4.*side,index=idx)
    if break_raw:
        raw.iloc[5] = -4.*side
    if gap:
        bars,raw = bars.drop(idx[5]),raw.drop(idx[5])
    activation = pd.DataFrame({"motion":0.,"charge":0.,"scale":1.},index=bars.index)
    shocks = {s:(bars.index == idx[2]) & (s == side) for s in (1,-1)}
    head = WarningMemory(activation,shocks,mode)
    trades,_,hold = simulate(bars,raw,raw,-raw,fixed_signals={idx[0]:side},policy=head)
    return idx,trades.iloc[0],hold,head.events


@pytest.mark.parametrize("side",[-1,1])
@pytest.mark.parametrize("step,reason,bar",[(0,"hold",6),(-1,"hold",6),(.25,"time",9)])
def test_confirm(side,step,reason,bar):
    idx,t,h,events = trial(side,step)
    assert t.reason == reason and t.exit_time == idx[bar]
    assert h.loc[idx[4]] > 0
    assert events[:2] == [(idx[4],idx[4],"warning",None),
        (idx[5],idx[4],"exit" if step<=0 else "reclaimed",step)]


def test_delay_exits_even_on_reclaim():
    idx,t,_,_ = trial(1,.25,mode="delay")
    assert t.reason == "hold" and t.exit_time == idx[6]


@pytest.mark.parametrize("gap,raw,reason",[(True,False,"gap"),(False,True,"signal")])
def test_forced_exits_override_confirmation(gap,raw,reason):
    idx,t,_,events = trial(-1,4,break_raw=raw,gap=gap)
    assert t.reason == reason and t.exit_time == idx[6]
    assert events[-1][2] == ("forced" if gap else "raw_exit")
