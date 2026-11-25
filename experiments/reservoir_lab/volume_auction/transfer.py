"""External-market transfer. Freeze source, full-year rule and time mapping."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

HASH="1577e60a7feab411e49da7a56c7052a64738cd1757cfd60aa11fd783ff43b60b"


def load_year(path):
    with path.open("rb") as f:
        if hashlib.file_digest(f,"sha256").hexdigest()!=HASH:raise ValueError("NQ archive checksum mismatch")
    f=pd.read_csv(path,usecols=["timestamp ET","open","high","low","close","volume"])
    stamps=pd.to_datetime(f.pop("timestamp ET"),format="%m/%d/%Y %H:%M")
    keep=(stamps.dt.weekday<5)&(stamps.dt.hour*60+stamps.dt.minute).between(571,960)
    b=f[keep].set_axis(stamps[keep].dt.tz_localize("America/New_York")-pd.Timedelta(minutes=1))
    b.index.name="bar_start"
    if b.index.duplicated().any() or not b.index.is_monotonic_increasing:raise ValueError("ambiguous session grid")
    sizes=b.groupby(b.index.date).size()
    full=sizes[sizes==390].index
    selected=next([d for d in full if d.year==year][:252] for year in sorted({d.year for d in full}) if sum(d.year==year for d in full)>=120)
    tape=b[np.isin(b.index.date,selected)]
    assert np.isfinite(tape.to_numpy()).all() and (tape.volume>=0).all()
    assert (tape.high>=tape[["open","close"]].max(axis=1)).all() and (tape.low<=tape[["open","close"]].min(axis=1)).all()
    return {f"NQ_{selected[0].year}":tape}
