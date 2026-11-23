"""Directional episode memory and two binary latches, observed at bar closes."""
import json
from pathlib import Path

import numpy as np
import pandas as pd


def anchor_state(raw, close, scale):
    cfg = json.loads(Path(__file__).with_name("weights.json").read_text())
    comparisons = np.array(cfg["comparison_weights"])
    gates = np.array(cfg["latch_weights"])
    direction, anchor, width = 0, np.nan, np.nan
    armed = retired = False
    rows = []
    for value, price, unit in zip(raw, close, scale, strict=True):
        side = np.sign(value) if np.isfinite(value) else 0
        if side != direction or side == 0:
            direction, anchor, width = side, np.nan, np.nan
            armed = retired = False
        if np.isnan(anchor) and abs(value) > cfg["anchor_hurdle_points"]:
            anchor, width = price, unit
        progress = side*(price-anchor)/width
        if np.isfinite(progress):
            favorable, returned = comparisons @ [progress, -progress] + cfg["comparison_bias"] >= 0
            armed, failed, prior = gates @ [armed, favorable, returned, retired] + cfg["latch_bias"] >= 0
            retired = failed or prior
        rows.append((value*(1-int(retired)), anchor, progress, bool(armed), bool(retired)))
    return pd.DataFrame(rows, index=raw.index,columns=["score","anchor","progress","armed","retired"])
