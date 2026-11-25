"""Observe a frozen original forecast and four-minute risk band on incoming bars."""
import argparse
from datetime import date, datetime, time
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time as clock

import numpy as np
import pandas as pd

from replay_lab import HERE, LAB, activations, verify_brain
from overlap import ExposureClock
from risk_study import summarize
sys.path.insert(0,str(LAB/"minute_observatory"))
from observer import collect, journal, NY

CORE=LAB.parent/"path_order"
SESSIONS={d:c for d,c in json.loads((CORE/"prospective.json").read_text())["sessions"].items() if d>="2026-11-25"}
FILES=("overlap.py","risk_head.py","risk_weights.json","forward.py","forward_protocol.md")


def setup(db):
    db.execute("CREATE TABLE IF NOT EXISTS calls(day TEXT, origin TEXT, made TEXT, raw REAL, band REAL, provisional_input INTEGER, PRIMARY KEY(day,origin))")
    db.execute("CREATE TABLE IF NOT EXISTS days(day TEXT PRIMARY KEY, plates TEXT, history TEXT, report TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)")


def step(day,b,received,db,source,feed_id,anomalies=0):
    key=day.isoformat()
    made=datetime.now(NY)
    if key not in SESSIONS or b.empty or str(b.index[0].date())!=key or len(set(b.index.date))!=1:
        raise ValueError("expected observations for one registered session")
    db.execute("BEGIN IMMEDIATE")
    setup(db)
    signature=hashlib.sha256(b"".join((HERE/f).read_bytes() for f in FILES)).hexdigest()
    for name,value in [("signature",signature),("feed",feed_id)]:
        db.execute("INSERT OR IGNORE INTO settings VALUES(?,?)",(name,value))
        if db.execute("SELECT value FROM settings WHERE key=?",(name,)).fetchone()[0]!=value:
            raise ValueError("source or frozen risk code changed; use a separate track")
    existing=db.execute("SELECT report FROM days WHERE day=?",(key,)).fetchone()
    if existing:
        db.commit()
        return json.loads(existing[0])
    previous=[d for d in SESSIONS if d<key]
    saved=[d for (d,) in db.execute("SELECT day FROM days ORDER BY day")]
    if saved!=previous:
        raise ValueError("registered predecessor missing; cumulative qualification cannot skip sessions")
    head=ExposureClock()
    if previous:
        plates,history=db.execute("SELECT plates,history FROM days WHERE day=?",(previous[-1],)).fetchone()
        head.plates=np.asarray(json.loads(plates));head.log_scale=float(head.plates.mean())
        head.history.extend(json.loads(history))
    a=activations(b,"reservoir")
    trace,labels=head.session(b,a)
    # A trade-price OHLC bar cannot span distinct transaction prices with zero contracts.
    # Preserve such inputs and flag dependent forecasts; never repair them from the future.
    bad=(b.volume==0)&(b.high>b.low)
    segment=a.age.eq(1).cumsum()
    suspect=bad.groupby(segment).cummax()
    eligible=(a.age>=32)&((b.index.hour*60+b.index.minute+5)<=955)
    when=datetime.now(NY).isoformat()
    calls=[(key,ts.isoformat(),when,float(a.reservoir.loc[ts]),float(trace.band.loc[ts]),int(suspect.loc[ts]))
           for ts in b.index[eligible]]
    db.executemany("INSERT OR IGNORE INTO calls VALUES(?,?,?,?,?,?)",calls)
    stamps={}
    for origin,first,raw,band,flag in db.execute("SELECT origin,made,raw,band,provisional_input FROM calls WHERE day=?",(key,)):
        ts=pd.Timestamp(origin)
        if (raw,band,flag)!=(float(a.reservoir.loc[ts]),float(trace.band.loc[ts]),int(suspect.loc[ts])):
            raise ValueError("previously issued forecast changed")
        stamps[ts]=pd.Timestamp(first)
    timely=sum(stamps[r.origin]<r.matures for r in labels.itertuples())
    ready=(len(b)==390 and b.index[0].time()==time(9,30) and b.index[-1].time()==time(15,59) and made>=b.index[-1]+pd.Timedelta(minutes=1))
    last=b.index[-1]
    report=dict(day=key,contract=SESSIONS[key],source=source,first_seen_hash=hashlib.sha256(b.to_csv().encode()).hexdigest(),
        asof=when,bar_count=len(b),settled=len(labels),issued_before_path_ended=int(timely),
        issued_before_path_began=int(sum(stamps[r.origin]<r.origin+pd.Timedelta(minutes=1) for r in labels.itertuples())),
        within_nine_seconds_of_close=int(sum(0<=(stamp-(ts+pd.Timedelta(minutes=1))).total_seconds()<=9 for ts,stamp in stamps.items())),
        moving_zero_volume_bars=int(bad.sum()),flagged_forecasts=int(suspect[eligible].sum()),revisions_or_late_additions=anomalies,
        last_bar=last.isoformat(),last_received=received[-1],next_open_raw_score=float(a.reservoir.iloc[-1]) if pd.notna(a.reservoir.iloc[-1]) else None,
        risk_halfwidth_pts=float(trace.band.iloc[-1]) if eligible.iloc[-1] else None,
        mode="after-close diagnostics" if ready else "partial session",complete=bool(ready),
        source_and_fills_independently_audited=False)
    if len(labels)>0:
        report["scorecard"]=summarize(labels)
    if ready:
        db.execute("INSERT INTO days VALUES(?,?,?,?)",(key,json.dumps(head.plates.tolist()),json.dumps(list(head.history)),json.dumps(report)))
    db.commit()
    return report


def refresh(args):
    verify_brain()
    day=args.day or datetime.now(NY).date()
    if day.isoformat() not in SESSIONS: raise ValueError("date outside the registered forward panel")
    contract=SESSIONS[day.isoformat()]
    b,source,digest=collect(day,contract,datetime.now(NY),args.csv)
    received=datetime.now(NY)
    b,stamps,anomalies=journal(args.out/"bars.sqlite",b,source,contract,received,digest)
    with sqlite3.connect(args.out/"forecast.sqlite") as db:
        r=step(day,b,stamps,db,source,str(args.csv.resolve()) if args.csv else source,anomalies)
    tmp=args.out/"latest.tmp";tmp.write_text(json.dumps(r,indent=2,allow_nan=False)+"\n");tmp.replace(args.out/"latest.json")
    print(r["last_bar"],r["mode"],r["risk_halfwidth_pts"],flush=True)
    return r["complete"]


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--out",required=True,type=Path)
    p.add_argument("--day",type=date.fromisoformat,default=datetime.now(NY).date());p.add_argument("--csv",type=Path)
    p.add_argument("--watch",action="store_true",help="observe this session until its complete grid is recorded or 16:30 ET")
    args=p.parse_args()
    args.out.mkdir(exist_ok=True,parents=True)
    if args.day.isoformat() not in SESSIONS: p.error("choose a registered full session")
    print(f"Paper risk recorder for {args.day} · {SESSIONS[args.day.isoformat()]} · first eligible session starts 09:30 ET",flush=True)
    while True:
        now=datetime.now(NY)
        if args.watch and now<datetime.combine(args.day,time(9,30),NY):
            clock.sleep(min(60,(datetime.combine(args.day,time(9,30),NY)-now).total_seconds()))
            continue
        try:
            if refresh(args): break
        except (OSError,ValueError,KeyError) as e:
            if not args.watch: raise
            print("Observation pending:",e,flush=True)
        if not args.watch or now>=datetime.combine(args.day,time(16,30),NY):break
        clock.sleep(1 if args.csv else 15)
