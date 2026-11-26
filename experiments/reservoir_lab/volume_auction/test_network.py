import numpy as np
import pandas as pd

from cascade import propagate
from impulse import encode
from network import features
from timing import timed


def tape(n=110):
    rng=np.random.default_rng(52);idx=pd.date_range("2026-09-22 14:10",periods=n,freq="min",tz="America/New_York")
    o=2000+np.cumsum(rng.integers(-25,26,n))/4;c=o+rng.integers(-16,17,n)/4
    return pd.DataFrame(dict(open=o,high=np.maximum(o,c)+1,low=np.minimum(o,c)-1,close=c,volume=rng.integers(200,4000,n)),index=idx)


def test_prefix_reflection_volume_units():
    b=tape();mirror=b.assign(open=4000-b.open,close=4000-b.close,high=4000-b.low,low=4000-b.high)
    d=features(b,field=propagate); reflected=features(mirror,field=propagate);launch=encode(b)
    np.testing.assert_allclose(reflected.score,-d.score,equal_nan=True)
    np.testing.assert_array_equal(reflected.event,-d.event)
    np.testing.assert_allclose(encode(mirror).weighted,-launch.weighted,equal_nan=True,atol=1e-10)
    pd.testing.assert_frame_equal(features(b.assign(volume=b.volume*8),field=propagate),d)
    for i in (15,31,55,92):
        pd.testing.assert_frame_equal(features(b.iloc[:i],field=propagate),d.iloc[:i])
        pd.testing.assert_frame_equal(encode(b.iloc[:i]),launch.iloc[:i])


def test_missing_measurement_and_gap_reset():
    b=tape();b.iloc[40,b.columns.get_loc("volume")]=0
    f=features(b,field=propagate)
    assert f.suspect.iat[40] and f.age.iat[40]==0 and f.age.iat[41]==1
    assert f.score.iloc[40:72].isna().all()
    assert encode(b).weighted.iloc[40:57].isna().all()
    skipped=b.drop(b.index[60])
    assert features(skipped).age.iat[60]==1


def test_pinned_price_head_formula():
    b=tape();l=encode(b)
    for j in range(16,len(b)):
        c=b.close.to_numpy();a=c[j-2]
        r=(b.high-b.low).iloc[j-15:j-1].mean()
        x=np.diff(c[j-16:j+1])/r
        bg=x[:14].sum()/7
        overhead=np.maximum(0,-np.cumsum(x[13::-1])).mean()
        raw=x[14:].sum()-bg-abs(bg)-(b.high.iat[j]-c[j])/r-2-overhead
        expected=r*min(np.clip(raw,0,1),2*max(0.,x[14:].min()))
        np.testing.assert_allclose(l.v08_long.iat[j],expected,atol=1e-12)


def test_four_minute_order_and_cutoff():
    b=tape();s=pd.Series(0.,index=b.index);s.iloc[[35,104]]=9
    t,m=timed(b,s)
    assert len(t)==1
    assert (t.entry_time.iat[0],t.exit_time.iat[0])==(b.index[36],b.index[40])
    assert m.iat[-1]==2*(b.open.iat[40]-b.open.iat[36])-6
