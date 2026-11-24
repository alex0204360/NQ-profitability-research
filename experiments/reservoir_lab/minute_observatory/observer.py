"""Local frozen-brain minute observer. Input bars are minute-start OHLCV."""
import argparse
import hashlib
import json
import math
import re
from io import BytesIO
import sqlite3
import sys
import time as clock
from datetime import datetime, timedelta
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd

HERE=Path(__file__).resolve().parent
CORE=HERE.parents[1]/"path_order"
sys.path.insert(0,str(CORE/"workbench"))
from session import activations, verify_brain
from execution import ENTRY_THRESHOLD_POINTS, FLATTEN_TIME, POINT_VALUE_USD
from session import FRICTION
from data import FIELDS, regular_hours

RELEASE_WEIGHT=json.loads((CORE/"reservoir.json").read_text())["state"][1][1]
NY=ZoneInfo("America/New_York")
MIN=pd.Timedelta(minutes=1)


def collect(day, contract, now, csv=None):
    if csv:
        payload=csv.read_bytes()
        f=pd.read_csv(BytesIO(payload))
        if not {"contract","timestamp_utc",*FIELDS}.issubset(f):
            raise ValueError("CSV needs contract, timestamp_utc and OHLCV")
        if not f.contract.eq(contract).all() or not f.timestamp_utc.astype(str).str.contains(r"(?:Z|[+-]\d\d:?\d\d)$").all():
            raise ValueError("expected a single dated contract and timezone-qualified timestamps")
        f.timestamp_utc=pd.to_datetime(f.timestamp_utc,utc=True)
        source="CSV · finalized bars"
    else:
        start=datetime.combine(day,datetime.min.time(),NY).replace(hour=9,minute=30)
        end=min(now,start.replace(hour=16,minute=1))
        if end<=start: raise ValueError("session has not opened")
        url=f"https://query1.finance.yahoo.com/v8/finance/chart/{contract}.CME?"+urlencode(
            dict(period1=int(start.timestamp()),period2=int(end.timestamp()),interval="1m",includePrePost="true"))
        with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=15) as r:
            payload=r.read()
        item,=json.loads(payload)["chart"]["result"]
        meta=item["meta"]
        if [meta.get(k) for k in ("symbol","instrumentType","dataGranularity","exchangeTimezoneName","exchangeName")] != [
                contract+".CME","FUTURE","1m","America/New_York","CME"]:
            raise ValueError("unexpected market data series")
        f=pd.DataFrame(item["indicators"]["quote"][0])[FIELDS]
        f["timestamp_utc"]=pd.to_datetime(item["timestamp"],unit="s",utc=True)
        # The last Yahoo candle can still be forming on the vendor's delayed clock.
        # Require a later vendor timestamp at/after the bar's end, including after 16:00.
        watermark=f.timestamp_utc.max()
        f=f[f.timestamp_utc.add(MIN)<=watermark].dropna()
        source="Yahoo · delayed"
    f=f[f.timestamp_utc.add(MIN)<=now]
    f=f[f.timestamp_utc==f.timestamp_utc.dt.floor("min")] if not csv else f
    b=regular_hours(f,day.isoformat(),day.isoformat())
    if any(abs(4*v-round(4*v))>1e-7 for v in b[FIELDS[:4]].to_numpy().flat):
        raise ValueError("off-tick MNQ quote")
    return b,source,hashlib.sha256(payload).hexdigest()


def journal(db,b,source,contract,received,digest):
    # Keep the first snapshot of each minute. A vendor correction or late older
    # minute is diagnostic and must never rewrite a decision already displayed.
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE IF NOT EXISTS bars (feed TEXT, contract TEXT, ts TEXT, values_json TEXT, received TEXT, PRIMARY KEY(feed,contract,ts))")
        c.execute("CREATE TABLE IF NOT EXISTS exceptions (feed TEXT, contract TEXT, ts TEXT, values_json TEXT, kind TEXT, received TEXT, PRIMARY KEY(feed,contract,ts,values_json))")
        c.execute("CREATE TABLE IF NOT EXISTS captures (feed TEXT, contract TEXT, received TEXT, hash TEXT)")
        c.execute("BEGIN IMMEDIATE")
        key=(source,contract)
        day=b.index[0].date().isoformat()
        saved=dict(c.execute("SELECT ts,values_json FROM bars WHERE feed=? AND contract=? AND substr(ts,1,10)=?",(*key,day)))
        last=max(saved,default="")
        for ts,row in b.iterrows():
            stamp=ts.isoformat()
            vals=json.dumps([float(row[k]) for k in FIELDS])
            if saved.get(stamp)==vals: continue
            if stamp<=last:
                kind="revision" if stamp in saved else "late backfill"
                c.execute("INSERT OR IGNORE INTO exceptions VALUES(?,?,?,?,?,?)",(*key,stamp,vals,kind,received.isoformat()))
            else:
                c.execute("INSERT INTO bars VALUES(?,?,?,?,?)",(*key,stamp,vals,received.isoformat()))
        c.execute("INSERT INTO captures VALUES(?,?,?,?)",(*key,received.isoformat(),digest))
        rows=list(c.execute("SELECT ts,values_json,received FROM bars WHERE feed=? AND contract=? AND substr(ts,1,10)=? ORDER BY ts",(*key,day)))
        anomalies=c.execute("SELECT count(*) FROM exceptions WHERE feed=? AND contract=? AND substr(ts,1,10)=?",(*key,day)).fetchone()[0]
    idx=pd.to_datetime([r[0] for r in rows],utc=True).tz_convert(NY)
    frozen=pd.DataFrame([json.loads(r[1]) for r in rows],index=idx,columns=FIELDS)
    return frozen,[r[2] for r in rows],anomalies


def observe(b,receipts=None):
    """Emit one prefix-safe decision per completed bar; fills use the observed next open."""
    a=activations(b,"reservoir")
    side=0
    pending=0
    entry=realized=peak=0.
    prev=None
    rows=[]
    for i,(bar,neuron) in enumerate(zip(b.itertuples(),a.itertuples(),strict=True)):
        ts=bar.Index
        gap=prev is not None and ts-prev!=MIN
        fill=""
        pnl=None
        if side and (gap or ts.time()>=FLATTEN_TIME or pending==2):
            pnl=side*(bar.open-entry)*POINT_VALUE_USD-FRICTION
            realized+=pnl
            fill=("Gap exit" if gap else "Cutoff exit" if ts.time()>=FLATTEN_TIME else "Forecast exit")
            side=0
        elif pending in (-1,1) and not gap and ts.time()<FLATTEN_TIME:
            side=pending
            entry=bar.open
            fill="Long entry" if side==1 else "Short entry"
        pending=0
        raw=neuron.reservoir
        if (ts+MIN).time()>=FLATTEN_TIME:
            decision="Scheduled flatten" if side else "Cutoff · flat"
        elif neuron.age<32:
            decision="Warming up"
        elif side and side*raw<=0:
            pending=2
            decision="Exit next open"
        elif not side and abs(raw)>ENTRY_THRESHOLD_POINTS:
            pending=1 if raw>0 else -1
            decision="Long next open" if pending==1 else "Short next open"
        else:
            decision="Hold" if side else "Stay flat"
        mark=realized+(side*(bar.close-entry)*POINT_VALUE_USD-FRICTION/2 if side else 0.)
        peak=max(peak,mark)
        rows.append(dict(bar=ts.isoformat(),decision_at=(ts+MIN).isoformat(),
            first_seen=receipts[i] if receipts else None,o=bar.open,h=bar.high,l=bar.low,c=bar.close,v=bar.volume,
            forecast=raw if math.isfinite(raw) else None,age=neuron.age,stock=neuron.stock,charge=neuron.charge,
            release=neuron.signed_release,range_scale=neuron.scale,
            new_points=neuron.scale*RELEASE_WEIGHT*neuron.signed_release,side=side,decision=decision,fill=fill,net=pnl,equity=mark,drawdown=peak-mark))
        prev=ts
    return rows


def atomic(path,data):
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(data)
    tmp.replace(path)


def publish(out,state):
    data=json.dumps(state,allow_nan=False,separators=(",",":"))
    atomic(out/"snapshot.html",(HERE/"dashboard.html").read_text().replace("__STATE__",data.replace("<",r"\u003c")))
    atomic(out/"state.json",data)


def refresh(args,out):
    now=datetime.now(NY)
    day=args.day or now.date()
    b,source,digest=collect(day,args.contract,now,args.csv)
    seen=datetime.now(NY)
    b,receipts,anomalies=journal(out/"journal.sqlite",b,source,args.contract,seen,digest)
    rows=observe(b,receipts)
    computed=datetime.now(NY)
    with sqlite3.connect(out/"journal.sqlite") as db:
        db.execute("CREATE TABLE IF NOT EXISTS calls (feed TEXT, contract TEXT, ts TEXT, computed TEXT, forecast REAL, decision TEXT, side INTEGER, PRIMARY KEY(feed,contract,ts))")
        db.executemany("INSERT OR IGNORE INTO calls VALUES(?,?,?,?,?,?,?)",
                       [(source,args.contract,r["bar"],computed.isoformat(),r["forecast"],r["decision"],r["side"]) for r in rows])
        calls={ts:(made,forecast,decision,side) for ts,made,forecast,decision,side in db.execute(
            "SELECT ts,computed,forecast,decision,side FROM calls WHERE feed=? AND contract=? AND substr(ts,1,10)=?",
            (source,args.contract,day.isoformat()))}
    for row in rows:
        made,forecast,decision,side=calls[row["bar"]]
        if (forecast,decision,side)!=(row["forecast"],row["decision"],row["side"]):
            raise ValueError("frozen decision differs from recorded call")
        row["first_computed"]=made
        row["decision_lag_seconds"]=(datetime.fromisoformat(made)-datetime.fromisoformat(row["decision_at"])).total_seconds()
    state=dict(day=day.isoformat(),contract=args.contract,source=source,asof=seen.isoformat(),rows=rows,
               revisions=anomalies,missing=int((b.index[-1]-pd.Timestamp(day,tz=NY).replace(hour=9,minute=30))/MIN)+1-len(rows),error=None)
    publish(out,state)
    print(f"{seen.isoformat(timespec='seconds')}  {len(rows)} bars  close {rows[-1]['decision_at']}  {rows[-1]['decision']}",flush=True)


class Dashboard(BaseHTTPRequestHandler):
    def __init__(self,*args,out,**kwargs):
        self.out=out
        super().__init__(*args,**kwargs)

    def do_GET(self):
        files={"/":("snapshot.html","text/html"),"/state.json":("state.json","application/json")}
        target=files.get(self.path.split("?")[0])
        if not target: return self.send_error(404)
        path=self.out/target[0]
        if not path.exists(): return self.send_error(503,"Waiting for completed bars")
        body=path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type",target[1]+"; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self,*args): pass


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--contract",default="MNQZ26")
    p.add_argument("--day",type=pd.Timestamp)
    p.add_argument("--csv",type=Path,help="growing CSV of finalized minute-start OHLCV bars")
    p.add_argument("--serve",action="store_true")
    p.add_argument("--through-close",action="store_true",help="stop polling at 16:15 ET and keep serving the last snapshot")
    p.add_argument("--port",type=int,default=8765)
    a=p.parse_args()
    a.day=a.day.date() if a.day else None
    if not re.fullmatch(r"MNQ[HMUZ]\d{2}",a.contract): p.error("expected dated MNQ symbol")
    verify_brain()
    a.out.mkdir(parents=True,exist_ok=True)
    if a.through_close and a.day is None:
        a.day=datetime.now(NY).date()
    if a.serve:
        http=ThreadingHTTPServer(("127.0.0.1",a.port),partial(Dashboard,out=a.out))
        Thread(target=http.serve_forever,daemon=True).start()
        print(f"Paper monitor at http://127.0.0.1:{a.port}",flush=True)
    while True:
        try: refresh(a,a.out)
        except Exception as e:
            if not a.serve: raise
            path=a.out/"state.json"
            state=json.loads(path.read_text()) if path.exists() else dict(day=str(a.day or datetime.now(NY).date()),
                        contract=a.contract,source="Awaiting data",asof=datetime.now(NY).isoformat(),rows=[],revisions=0,missing=0)
            publish(a.out,dict(state,error=str(e)))
            print(f"Feed unavailable: {e}",flush=True)
        if not a.serve: break
        if a.through_close and datetime.now(NY)>=datetime.combine(a.day, datetime.min.time(),NY).replace(hour=16,minute=15):
            print("Session collection ended. Serving the saved session.",flush=True)
            from threading import Event
            Event().wait()
        clock.sleep(1 if a.csv else 15)


if __name__=="__main__": main()
