"""Inspect all three frozen directional heads at the last completed bar of a supplied session."""
import argparse
import json
from datetime import datetime
from pathlib import Path
import re

import numpy as np
import pandas as pd

from network import features
from cascade import propagate
from impulse import encode

FIELDS=["open","high","low","close","volume"]


def snapshot(b):
    trace=features(b,field=propagate)
    packet=trace.iloc[-1]
    controls=features(b,"equal_volume",field=propagate).iloc[-1]
    launch=encode(b).iloc[-1]
    def value(x):
        return float(x) if np.isfinite(x) else None
    def entry(x):
        return ("long" if x>3 else "short" if x < -3 else "flat") if np.isfinite(x) else "warmup"
    eligible=(b.index[-1]+pd.Timedelta(minutes=1)).time()<pd.Timestamp("15:55").time()
    return dict(bar_start=b.index[-1].isoformat(),decision_close=(b.index[-1]+pd.Timedelta(minutes=1)).isoformat(),
                before_entry_cutoff=eligible,suspect_volume=bool(packet.suspect),
                units="MNQ points; closed-bar diagnostics",inventory_score=value(packet.score),
                inventory_flat_entry=entry(packet.score) if eligible else "cutoff",
                cascade_event=int(packet.event),cascade_target=value(packet.target) if packet.event else None,
                cascade_invalidation=value(packet.invalidation) if packet.event else None,
                cascade_equal_mass_event=int(controls.event),launch_score=value(launch.weighted),
                launch_equal_mass_score=value(launch.equal_mass),launch_flat_entry=entry(launch.weighted) if eligible else "cutoff")


def read(path,contract):
    f=pd.read_csv(path)
    if not f.contract.eq(contract).all() or not re.fullmatch(r"MNQ[HMUZ]\d{2}",contract):
        raise ValueError("expected exactly the requested dated MNQ contract")
    if not f.timestamp_utc.astype(str).str.contains(r"(?:Z|[+-]\d\d:?\d\d)$").all():
        raise ValueError("timezone-qualified minute-start timestamps required")
    ts=pd.DatetimeIndex(pd.to_datetime(f.timestamp_utc,utc=True)).tz_convert("America/New_York")
    if not ts.is_unique or not ts.is_monotonic_increasing or not (ts==ts.floor("min")).all():
        raise ValueError("timestamps must be unique ordered minute starts")
    b=f[FIELDS].astype(float).set_axis(ts).between_time("09:30","15:59")
    b=b[b.index+pd.Timedelta(minutes=1)<=pd.Timestamp.now(tz="UTC")]
    if b.empty or len(set(b.index.date))!=1:raise ValueError("supply one session of completed bars")
    if b.index[0].strftime("%H:%M")!="09:30":raise ValueError("start the session at 09:30 ET")
    if (not np.isfinite(b).all().all() or (b.volume<0).any() or
        (b.low>b[["open","close"]].min(axis=1)).any() or (b.high<b[["open","close"]].max(axis=1)).any()
        or not np.allclose(b[FIELDS[:4]]*4,np.rint(b[FIELDS[:4]]*4),rtol=0,atol=1e-7)):
        raise ValueError("invalid MNQ OHLCV")
    return b


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("csv",type=Path);p.add_argument("--contract",required=True)
    args=p.parse_args();print(json.dumps(snapshot(read(args.csv,args.contract)),indent=2,allow_nan=False))
