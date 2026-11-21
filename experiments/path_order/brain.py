"""Manually weighted recurrent product network. Input rows are completed bars."""
from pathlib import Path
import json

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent


def weights(name="area"):
    return json.loads((HERE / f"{name}.json").read_text())


def area_activations(bars):
    cfg = weights()
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
               "area", "symmetric", "trend"]
    return pd.DataFrame(rows, columns=columns, index=bars.index)

def transport(encoded, cfg, charge_weights):
    rectifier = np.asarray(cfg["rectifier"])
    bias = np.asarray(cfg["rectifier_bias"])
    routing = np.asarray(cfg["routing"])
    update = np.asarray(cfg["state"])
    readout = np.asarray(cfg["readout"])
    stock, forecast = 0., 0.
    rows = []
    for age, effort, motion in encoded[["age", "effort", "motion"]].itertuples(index=False):
        if age == 1:
            stock, forecast = 0., 0.
        hinges = np.maximum(0., rectifier @ [effort, motion] + bias)
        charge = max(0., charge_weights @ np.r_[effort, hinges[:2]])
        retained, signed = stock * (routing @ np.r_[1., hinges])
        stock, forecast = update @ [retained, signed, forecast, charge]
        rows.append((charge, stock, signed, readout @ [stock, forecast]))
    return np.asarray(rows)


def activations(bars, name="area"):
    encoded = area_activations(bars)
    if name == "area":
        return encoded
    if name not in ("reservoir", "volume_control"):
        raise ValueError(f"unknown circuit {name!r}")
    cfg = weights("reservoir")
    key = "charge" if name == "reservoir" else "charge_control"
    state = transport(encoded, cfg, np.asarray(cfg[key]))
    encoded[["charge", "stock", "signed_release"]] = state[:, :3]
    encoded[name] = (state[:, 3] * encoded.scale).where(encoded.area.notna())
    return encoded
