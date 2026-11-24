"""Check prefix decisions, exact historical marks and fills, and source correction handling."""
import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from observer import HERE, MIN, NY, FIELDS, observe, journal, publish
from session import activations, replay
sys.path.insert(0,str(HERE.parent/"tick_exit"))
from experiment import get_panels


def check(b):
    a=activations(b,"reservoir")
    trades,marks=replay(b,a.reservoir,cost=6.)
    rows=observe(b)
    np.testing.assert_array_equal([r["equity"] for r in rows],marks)
    open_fills=[(pd.Timestamp(r["bar"]),r["o"],r["fill"]) for r in rows if r["fill"].endswith("entry")]
    close_fills=[(pd.Timestamp(r["bar"]),r["o"],r["net"]) for r in rows if r["net"] is not None]
    assert open_fills==[(t.entry_time,t.entry,t.side.title()+" entry") for t in trades.itertuples()]
    assert close_fills==[(t.exit_time,t.exit,t.net_usd) for t in trades.itertuples()]
    for n in [1,31,32,len(b)//2,len(b)-1]:
        assert observe(b.iloc[:n])==rows[:n]
    return rows


def run(scratch,day_source,example):
    sessions=0
    for panel in get_panels(scratch).values():
        for _,b in panel.groupby(panel.index.date):
            check(b)
            sessions+=1
    raw=day_source.read_bytes()
    import hashlib
    ref=json.loads((HERE.parent/"paper_sessions/2026-11-23/scorecard.json").read_text())
    assert hashlib.sha256(raw).hexdigest()==ref["source_sha256"]
    item,=json.loads(raw)["chart"]["result"]
    b=pd.DataFrame(item["indicators"]["quote"][0],index=pd.to_datetime(item["timestamp"],unit="s",utc=True).tz_convert(NY))[FIELDS]
    rows=check(b)
    assert rows[-1]["equity"]==-645 and max(r["drawdown"] for r in rows)==1273.5
    with TemporaryDirectory() as tmp:
        db=Path(tmp)/"audit.sqlite"
        seen=b.index[-1]+MIN
        initial=b.iloc[[0,2,3]]
        journal(db,initial,"test","MNQZ26",seen,"synthetic")
        extra=b.iloc[:5].copy()
        extra.iloc[0,4]+=1
        frozen,receipts,exceptions=journal(db,extra,"test","MNQZ26",seen+MIN,"synthetic2")
        assert exceptions==2 and frozen.index.tolist()==b.index[[0,2,3,4]].tolist()
        assert frozen.iloc[0,4]==b.iloc[0,4] and receipts[-1]==(seen+MIN).isoformat()
        assert journal(db,extra,"test","MNQZ26",seen+2*MIN,"synthetic3")[2]==2
    example.mkdir(exist_ok=True,parents=True)
    publish(example,dict(day="2026-11-23",contract="MNQZ26",source="Archived session replay",rows=rows,
                         asof=(b.index[-1]+MIN).isoformat(),missing=0,revisions=0,error=None))
    print(f"Every observed equity mark and entry/exit matched across {sessions+1} sessions.")


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for key in ("scratch","nov23_source","example"): p.add_argument(key,type=Path)
    a=p.parse_args()
    run(a.scratch,a.nov23_source,a.example)
