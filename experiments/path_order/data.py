"""Load only the registered discovery parts or an explicitly supplied temporal panel."""
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

SOURCE_COMMIT = "8336fe8"
HASHES = [
    "3430116d80a7e4e2b9e2b2ed34315dc5255d2433620b737c96055556312176f2",
    "a7a64421e57fa8142a7c07f4415c719981c7d6020d50c068749806a0aff3eb34",
    "514249caa15cc110b289c5c48b2c8afa44c1d602d2174e5b7c393bf67a4c4a4b",
    "a218f1228416cd191d38d1841e66a75b2eb677f87448f42b8f9a120388816933",
    "b2777b42a4ef96037c868e4664e9142aac8ecb010abf4e4e65d2b59b6a28bff6",
    "bcf54e4b620996c1f4c28cda92f442f473573e042319c9eb9e1e810dc15a1114",
]
FIELDS = ["open", "high", "low", "close", "volume"]


def regular_hours(raw, start, end):
    t = pd.DatetimeIndex(pd.to_datetime(raw["timestamp_utc"], utc=True)).tz_convert("America/New_York")
    if not t.is_unique or not t.is_monotonic_increasing:
        raise ValueError("timestamps must be strictly increasing")
    day = t.strftime("%Y-%m-%d")
    use = (day >= start) & (day <= end) & (t.weekday < 5)
    bars = raw.set_index(t).loc[use, FIELDS].between_time("09:30", "15:59").astype(float)
    if bars.empty or (bars.index != bars.index.floor("min")).any():
        raise ValueError("missing or off-minute sample")
    if (not np.isfinite(bars).all().all() or (bars.volume < 0).any()
            or (bars.low > bars[["close", "open"]].min(axis=1)).any()
            or (bars.high < bars[["close", "open"]].max(axis=1)).any()):
        raise ValueError("invalid OHLCV")
    return bars


def discovery(directory):
    frames = []
    for i, digest in enumerate(HASHES, start=1):
        path = Path(directory) / f"MNQ_Yahoo_1m_20260913_20261012_part{i:02d}.csv"
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"hash mismatch for {path.name}")
        frames.append(pd.read_csv(path))
    return regular_hours(pd.concat(frames, ignore_index=True), "2026-09-14", "2026-10-09")
