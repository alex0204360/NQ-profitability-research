"""Manually weighted recurrent product network. Input rows are completed bars."""
from pathlib import Path
import json

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent


def weights(name="area"):
    return json.loads((HERE / f"{name}.json").read_text())


def activations(bars, name="area"):
    cfg = weights(name)
    left, right, update, integrate = (
        np.asarray(cfg[k], dtype=float) for k in ("left", "right", "memory", "pair_memory")
    )
    decay = cfg["range_and_volume_decay"]
    rows = []
    prev_time = None
    for bar in bars.itertuples():
        spread = bar.high - bar.low
        volume = np.log2(1 + bar.volume)
        if prev_time is None or bar.Index - prev_time != pd.Timedelta(minutes=1):
            mem = np.zeros(2)
            pair = np.zeros(2)
            log_vol, width, last = volume, max(spread, cfg["tick"]), bar.close
            age = 0
        scale = max(cfg["tick"], width)
        effort = np.clip(volume - log_vol, -cfg["effort_clip_octaves"], cfg["effort_clip_octaves"])
        motion = np.clip((bar.close - last) / scale, -cfg["motion_clip_ranges"], cfg["motion_clip_ranges"])
        x = np.array([*mem, effort, motion])
        gates = (left @ x) * (right @ x)
        pair = integrate @ np.r_[pair, gates]
        mem = update @ x
        age += 1
        area = float(pair @ cfg["readout"])
        symmetric = float(pair @ cfg["symmetric_control"])
        trend = float(mem @ cfg["trend_control"])
        heads = [scale * s if age >= cfg["warmup_bars"] else np.nan
                 for s in (area, symmetric, trend)]
        rows.append((age, scale, effort, motion, *mem, *gates, *pair, *heads))
        log_vol = decay * log_vol + (1 - decay) * volume
        width = decay * width + (1 - decay) * spread
        last, prev_time = bar.close, bar.Index
    columns = ["age", "scale", "effort", "motion", "effort_memory", "motion_memory",
               "effort_first_gate", "motion_first_gate", "effort_first", "motion_first",
               name, "symmetric", "trend"]
    return pd.DataFrame(rows, columns=columns, index=bars.index)
