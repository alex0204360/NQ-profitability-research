from datetime import datetime
import math
import sqlite3

import numpy as np
import pandas as pd
import pytest

from bridge import apply
from capacitor import circuit
import forward
from overlap import ExposureClock
from replay_lab import activations
from risk_head import CFG, INITIAL


def bars(n=100,day="2026-11-25"):
    idx=pd.date_range(f"{day} 09:30",periods=n,freq="min",tz="America/New_York")
    rng=np.random.default_rng(32)
    o=2000+np.cumsum(rng.integers(-28,29,n))/4
    c=o+rng.integers(-12,13,n)/4
    return pd.DataFrame(dict(open=o,close=c,high=np.maximum(o,c)+1.,low=np.minimum(o,c)-1.,
                             volume=rng.integers(20,900,n)),index=idx)


def test_loaded_cannot_discharge_more_than_stored():
    b=bars(5);b.close=[100.,100.,108.,109.,107.]
    a=pd.DataFrame(dict(age=[1,2,3,4,5],reservoir=np.ones(5),scale=np.ones(5),signed_release=[0,4,0,0,0]),index=b.index)
    d=circuit(b,a)
    assert d.loaded.tolist()==[0.,3.5,0.,0.,0.]
    assert d.delivered.tolist()==[0.,0.,3.5,0.,0.]
    assert d.unloaded.iloc[-1]>0


def test_closed_prefix_before_gap_and_after_reset():
    b=bars().drop(bars().index[48]);a=activations(b,"reservoir")
    c=circuit(b,a);d,rec=apply(b,a,c);h,labels=ExposureClock().session(b,a)
    for n in (32,37,48,49,85):
        ba=b.iloc[:n];aa=activations(ba,"reservoir")
        cc=circuit(ba,aa);dd,rr=apply(ba,aa,cc);hh,ll=ExposureClock().session(ba,aa)
        for sliced,full in [(cc,c),(dd,d),(hh,h)]:pd.testing.assert_frame_equal(sliced,full.iloc[:n])
        for partial,whole in [(rr,rec),(ll,labels)]:
            if len(partial):pd.testing.assert_frame_equal(partial,whole[whole.matures<=ba.index[-1]].reset_index(drop=True))
    assert ((labels.matures-labels.origin)==pd.Timedelta(minutes=5)).all()
    assert (d.loc[b.index[48],["w_original","w_loaded","w_zero"]].to_numpy()==np.ones(3)/3).all()
    assert (rec.origin.dt.hour*60+rec.origin.dt.minute<=950).all()


def test_label_close_cannot_contaminate_preceding_open_outcome():
    b=bars();a=activations(b,"reservoir")
    r,l=ExposureClock().session(b,a)
    row=l.iloc[0]
    t=b.index.get_loc(row.origin)
    held=b.iloc[t+1:t+5]
    start=held.open.iloc[0]; end=b.open.iat[t+5]
    assert row.travel==max(max(held.high.max(),end)-start,start-min(held.low.min(),end))
    corrupt=b.copy();corrupt.loc[row.matures,"high"]+=10000
    _,other=ExposureClock().session(corrupt,activations(corrupt,"reservoir"))
    assert other.iloc[0].travel==row.travel


def test_four_clocks_conserve_integrated_error():
    c=ExposureClock();b=bars();a=activations(b,"reservoir");_,l=c.session(b,a)
    errors=((l.travel>l.band).astype(float)-(1-CFG["coverage"])).sum()
    assert c.log_scale==pytest.approx(math.log(INITIAL)+CFG["log_gain"]*errors/4)


def test_forward_duplicate_restart_and_next_date(tmp_path,monkeypatch):
    class FixedClock(datetime):
        @classmethod
        def now(cls,tz=None): return cls(2026,12,1,18,0,tzinfo=tz)
    monkeypatch.setattr(forward,"datetime",FixedClock)
    def step(db,b):
        return forward.step(b.index[0].date(),b,[b.index[-1].isoformat()]*len(b),db,"synthetic","fixture")
    day=bars(390); day.iloc[40,day.columns.get_loc("volume")]=0
    with sqlite3.connect(tmp_path/"j.db") as db:
        assert step(db,day.iloc[:100])["flagged_forecasts"]>0
    with sqlite3.connect(tmp_path/"j.db") as db:
        r=step(db,day)
        assert r["complete"] and r["settled"]==350 and r["issued_before_path_ended"]==0
        assert step(db,day)==r
        assert db.execute("select count(*) from calls").fetchone()[0]==350
        nextday=bars(65,"2026-11-30")
        assert step(db,nextday)["settled"]==29
        head=ExposureClock();head.session(day,activations(day,"reservoir"))
        h,_=head.session(nextday,activations(nextday,"reservoir"))
        assert db.execute("select band from calls where day='2026-11-30' order by origin desc limit 1").fetchone()[0]==h.band.iat[-1]
