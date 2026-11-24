"""Sharp OHLC-order bounds for marked drawdown on an identical frozen ledger."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from evaluate_entry import HERE, LAB, get_panels


def bounds(bars,trades):
    enters={t.entry_time:t for t in trades.itertuples()}
    exits={t.exit_time:t for t in trades.itertuples()}
    realized=0.
    position=None
    peak=low_bound=high_bound=0.
    close_peak=close_dd=0.
    for bar in bars.itertuples():
        ts=bar.Index
        if ts in exits:
            assert position==exits[ts]
            realized+=position.net_usd
            position=None
        if ts in enters:
            assert position is None
            position=enters[ts]
        if position:
            slope=2 if position.side=="long" else -2
            def mark(price):
                return realized+slope*(price-position.entry)-3.
            opened,closed=mark(bar.open),mark(bar.close)
            low,high=sorted((mark(bar.low),mark(bar.high)))
        else:
            opened=closed=low=high=realized
        # Account low then high minimizes intrabar drawdown. High then low
        # maximizes it. Both orders start and end at the same marks and share
        # the same running peak at the end of this bar.
        peak=max(peak,opened)
        common=max(peak-low,high-closed)
        low_bound=max(low_bound,common)
        high_bound=max(high_bound,common,high-low)
        peak=max(peak,high)
        close_peak=max(close_peak,closed)
        close_dd=max(close_dd,close_peak-closed)
    assert position is None and realized==trades.net_usd.sum()
    assert close_dd<=low_bound<=high_bound
    return dict(net=realized,close_dd=close_dd,intraminute_min_dd=low_bound,intraminute_max_dd=high_bound)


def read_ledger(path):
    t=pd.read_csv(path)
    for k in ("entry_time","exit_time"):
        t[k]=pd.to_datetime(t[k],utc=True).dt.tz_convert("America/New_York")
    return t


def run(scratch,raw,out):
    frames=get_panels(scratch)
    archive=pd.concat(list(frames.values())).sort_index()
    parent=LAB/"warning_confirmation/results"
    scores=json.loads((parent/"results.json").read_text())
    combined=read_ledger(parent/"trades.csv")
    entry=read_ledger(out/"trades.csv")
    policies={"original":combined[combined["mode"]=="original"],"confirmation":combined[combined["mode"]=="confirm"],
              "corroborated":entry[entry.policy=="corroborated"]}
    days=archive.index.strftime("%Y-%m-%d")
    report={}
    for g,mask in [("earlier20",days<"2026-11"),("november14",days>="2026-11"),("nov19",days=="2026-11-19"),
                   ("other13",(days>="2026-11") & (days!="2026-11-19"))]:
        b=archive.loc[mask]
        report[g]={}
        for name,ledger in policies.items():
            t=ledger[ledger.entry_time.isin(b.index)]
            row=bounds(b,t)
            if name!="corroborated":
                base=scores[g]["confirm" if name=="confirmation" else "original"]
                assert (row["net"],row["close_dd"])==(base["net"],base["marked_drawdown"])
            report[g][name]=row
    from verify import FIELDS, NY
    item,=json.loads(raw.read_bytes())["chart"]["result"]
    b=pd.DataFrame(item["indicators"]["quote"][0],index=pd.to_datetime(item["timestamp"],unit="s",utc=True).tz_convert(NY))[FIELDS]
    t=read_ledger(LAB/"paper_sessions/2026-11-23/base-trades.csv")
    report["nov23"]={"original":bounds(b,t)}
    (out/"risk-bounds.json").write_text(json.dumps(report,indent=2)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("scratch","nov23","out"): p.add_argument(k,type=Path)
    a=p.parse_args()
    run(a.scratch,a.nov23,a.out)
