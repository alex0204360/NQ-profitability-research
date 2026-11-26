"""After-score accounting and unchanged closing-clock benchmark transport."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def decompose(trades):
    longs = trades.query("model == 'always_long'").set_index("entry_time").net_usd
    selected = trades.query("model == 'auction'").set_index("entry_time")
    kept_long = longs.reindex(selected.index)
    assert kept_long.notna().all()
    missed = longs[~longs.index.isin(selected.index)].sum()
    flips = selected.net_usd - kept_long
    result = dict(always_long=float(longs.sum()), long_on_chosen_dates=float(kept_long.sum()),
                  foregone_long_net=float(missed), changing_side=float(flips.sum()),
                  short_calls=int((selected.side=="short").sum()), auction_net=float(selected.net_usd.sum()))
    assert result["auction_net"]==result["always_long"]-missed+flips.sum()
    return result


def benchmark(path):
    # The earlier transfer left 2025 sealed. Restrict reading price fields to
    # the registered research years before using any record in calculations.
    with path.open("rb") as f:
        assert hashlib.file_digest(f,"sha256").hexdigest()=="1577e60a7feab411e49da7a56c7052a64738cd1757cfd60aa11fd783ff43b60b"
    b = pd.read_csv(path,usecols=["timestamp ET","open"])
    b.index=pd.to_datetime(b.pop("timestamp ET"),format="%m/%d/%Y %H:%M")
    b=b[b.index.year.isin([2023,2024]) & (b.index.weekday<5)].between_time("09:31","16:00")
    assert b.index.is_unique
    days=b.groupby(b.index.normalize()).size()
    b=b[b.index.normalize().isin(days[days==390].index)]
    def opens(label):
        s=b.at_time(label).open
        return s.set_axis(s.index.normalize())
    # This pinned archive uses assumed bar-END stamps.
    points=opens("15:56")-opens("15:31")
    assert np.isfinite(points).all()
    return {str(y):dict(sessions=len(g),points=float(g.sum()),native_NQ_net=float(20*g.sum()-14.5*len(g)),
                        MNQ_equivalent_on_NQ_prices=float(2*g.sum()-6*len(g))) for y,g in points.groupby(points.index.year)}


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("result_root",type=Path);p.add_argument("nq",type=Path);args=p.parse_args()
    result={}
    for track in ("external","discovery"):
        t=pd.read_csv(args.result_root/track/"trades.csv.gz")
        result[track]={k:decompose(g) for k,g in t.groupby("panel")}
    result["historical_NQ_transfer"]=benchmark(args.nq)
    (args.result_root/"closing-attribution.json").write_text(json.dumps(result,indent=2)+"\n")
