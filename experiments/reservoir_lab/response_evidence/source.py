"""Verify the pinned external inputs; publish only coverage and aggregate QA."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

COMMIT = "60abd3fb6369c6ce0b6a4a65b0f2562fc96b1264"
FILES = {
    "MNQ.csv": ("1min", "129623f45308a98a1a345473ac5fe4d03d5d53f7dd177a608d946eb3d3d6ea99"),
    "MNQ_5min.csv": ("5min", "1e42bc9a8a682c19e7cd460ab003b522b8643bda23b70e5f8235633d1ccf08f4"),
}


def external(root, out):
    bars = []
    for file, (_, digest) in FILES.items():
        path = root/file
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError(f"source mismatch: {file}")
        b = pd.read_csv(path)
        b.index = pd.DatetimeIndex(pd.to_datetime(b.pop("datetime"), utc=True)).tz_convert("America/New_York")
        if not b.index.is_monotonic_increasing or not b.index.is_unique:
            raise ValueError("ambiguous timestamps")
        bars.append(b)
    minute, five = bars
    rth = minute.between_time("09:30","15:59")
    sizes = rth.groupby(rth.index.date).size()
    dates = pd.bdate_range(minute.index[0].date(), minute.index[-1].date()).date
    keep = [d for d in dates if sizes.get(d,0)==390]
    clean = rth[np.isin(rth.index.date,keep)]
    assert len(clean)>0 and (clean.index.second==0).all() and np.isfinite(clean.to_numpy()).all()
    assert (clean.volume>=0).all() and (clean.high>=clean[["open","close"]].max(axis=1)).all() and (clean.low<=clean[["open","close"]].min(axis=1)).all()
    assert np.allclose(4*clean[["open","high","low","close"]]%1,0)
    rollup = clean.resample("5min").agg(dict(open="first",high="max",low="min",close="last",volume="sum")).dropna()
    ref = five.reindex(rollup.index)[rollup.columns]
    same = rollup.eq(ref)
    report = dict(source_commit=COMMIT, hashes={k:v[1] for k,v in FILES.items()},included_dates=list(map(str,keep)),
                  excluded_weekdays={str(d):int(sizes.get(d,0)) for d in dates if d not in keep},
                  overlap_5min=int(ref.open.notna().sum()),total_groups=len(ref),exact_ohlcv=int(same.all(axis=1).sum()),
                  exact_by_column=same.sum().astype(int).to_dict(),zero_volume_minutes=int((clean.volume==0).sum()))
    out.mkdir(exist_ok=True,parents=True)
    (out/"source.json").write_text(json.dumps(report,indent=2)+"\n")
    return {"external":clean}
