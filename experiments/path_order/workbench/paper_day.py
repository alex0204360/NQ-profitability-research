"""After-close, one-session MNQ paper replay with optional sub-minute quote audit."""
import argparse
import hashlib
import json
from datetime import date, datetime, time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from session import run_day, save_chart, verify_brain
from data import regular_hours, FIELDS
from quote_audit import audit

NY = ZoneInfo("America/New_York")


def completed(day, now):
    if day.weekday() > 4 or now < datetime.combine(day, time(16), NY):
        raise ValueError("A completed full weekday daytime session through 16:00 New York is required.")


def from_yahoo(day, contract):
    symbol = f"{contract}.CME"
    begin = datetime.combine(day, time(9,30), NY)
    end = datetime.combine(day, time(16), NY)
    query = urlencode(dict(period1=int(begin.timestamp()), period2=int(end.timestamp()), interval="1m"))
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}"
    with urlopen(Request(url, headers={"User-Agent":"Mozilla/5.0"}), timeout=45) as response:
        payload = response.read()
    chart = json.loads(payload)["chart"]
    if chart["error"] or not chart["result"]:
        raise ValueError(f"no Yahoo result for {symbol}: {chart['error']}")
    item, = chart["result"]
    meta = item["meta"]
    if (meta["symbol"] != symbol or meta["instrumentType"] != "FUTURE" or
            meta["dataGranularity"] != "1m" or meta["exchangeTimezoneName"] != "America/New_York"):
        raise ValueError("unexpected symbol or series metadata")
    q, = item["indicators"]["quote"]
    rows = pd.DataFrame({k:q[k] for k in FIELDS})
    rows["timestamp_utc"] = pd.to_datetime(item["timestamp"], unit="s", utc=True)
    rows["contract"] = contract
    return rows.dropna(subset=FIELDS), payload, url


def prepare(raw, day, contract, kind):
    if "timestamp_utc" not in raw.columns:
        raise ValueError("expected a timezone-qualified timestamp_utc column")
    raw = raw.copy()
    stamp = pd.DatetimeIndex(pd.to_datetime(raw.timestamp_utc, format="ISO8601"))
    if stamp.tz is None or stamp.hasnans:
        raise ValueError("timestamp_utc must include a timezone offset")
    stamp = stamp.tz_convert("UTC")
    raw["timestamp_utc"] = stamp - (pd.Timedelta(minutes=1) if kind == "end" else pd.Timedelta(0))
    on_day = raw.timestamp_utc.dt.tz_convert(NY).dt.date.eq(day)
    raw = raw.loc[on_day]
    if "contract" in raw and not raw.contract.eq(contract).all():
        raise ValueError("the input must contain the requested individual contract only")
    bars = regular_hours(raw, day.isoformat(), day.isoformat())
    if len(bars) > 390 or len(bars) < 2 or (bars.index.to_series().diff() == pd.Timedelta(minutes=1)).sum() == 0:
        raise ValueError("expected one-minute bars, including consecutive observations")
    if (bars.index[0].time(),bars.index[-1].time()) != (time(9,30), time(15,59)):
        raise ValueError("incomplete daytime session: require 09:30 and 15:59 minute-start bars")
    if not np.allclose(bars[FIELDS[:4]]*4, np.rint(bars[FIELDS[:4]]*4), rtol=0, atol=1e-8):
        raise ValueError("prices are off the MNQ quarter-point tick grid")
    return bars


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", type=date.fromisoformat, default=date(2026,11,23))
    p.add_argument("--contract", default="MNQZ26", help="contract attested by the source")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--bars", type=Path)
    source.add_argument("--fetch", action="store_true", help="fetch dated Yahoo contract after close")
    p.add_argument("--stamp", choices=["start","end"], help="required for CSV input")
    p.add_argument("--quotes", type=Path, help="one-day timestamp_utc,contract,bid,ask CSV")
    p.add_argument("--latency-seconds", type=float, default=9)
    p.add_argument("--out", required=True, type=Path, help="new output directory")
    args = p.parse_args()
    completed(args.date, datetime.now(NY))
    verify_brain()
    if args.out.exists():
        raise ValueError("output already exists; use a new directory for a distinct run")
    if args.bars and not args.stamp:
        p.error("--bars requires --stamp start or --stamp end")
    if args.fetch and args.stamp == "end":
        p.error("Yahoo replay assumes minute-start bars")
    if args.fetch:
        raw, payload, origin = from_yahoo(args.date, args.contract)
        source_name = "raw-chart.json"
    else:
        payload = args.bars.read_bytes()
        raw = pd.read_csv(args.bars)
        origin, source_name = args.bars.name, "source.csv"
    kind = args.stamp or "start"
    bars = prepare(raw, args.date, args.contract, kind)
    chart,stats,base,guard,equity,guarded,neurons = run_day(bars)
    stats.update(contract=args.contract, source=origin, source_sha256=hashlib.sha256(payload).hexdigest(),
                 source_stamp=kind, fill="next minute open proxy, $6 per round trip",
                 contract_identity="column or source symbol" if "contract" in raw else "caller supplied",
                 quote_audit="No second-resolution quote evidence supplied")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=args.out.parent) as tmp:
        stage = Path(tmp)/"session"
        stage.mkdir()
        (stage/source_name).write_bytes(payload)
        if args.quotes:
            quotes = pd.read_csv(args.quotes)
            stats["quote_audit"] = dict(latency_seconds=args.latency_seconds,
                quote_sha256=hashlib.sha256(args.quotes.read_bytes()).hexdigest(),
                guard_trigger="frozen minute-mark reference equity")
            for name, trades in [("base",base), ("guard",guard)]:
                quoted,summary = audit(trades,quotes,args.contract,args.latency_seconds)
                quoted.to_csv(stage/f"{name}-quote-audit.csv",index=False)
                stats["quote_audit"][name] = {k:None if pd.isna(v) else v for k,v in summary.items()}
        base.to_csv(stage/"base-trades.csv",index=False)
        guard.to_csv(stage/"guard-trades.csv",index=False)
        neurons.assign(base_equity=equity,guarded_equity=guarded).to_csv(stage/"activations.csv")
        save_chart([chart],stage/"trades.html")
        (stage/"scorecard.json").write_text(json.dumps(stats,indent=2,allow_nan=False)+"\n")
        stage.rename(args.out)
    print(json.dumps(stats, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
