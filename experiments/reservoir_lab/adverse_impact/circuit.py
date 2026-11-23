"""Directional, one-bar-delayed adverse impact. No orders or forward labels here."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

CFG = json.loads(Path(__file__).with_name("weights.json").read_text())


def directional_state(bars, activation, side, with_volume=True):
    if side not in (-1, 1) or not bars.index.equals(activation.index):
        raise ValueError("expected an aligned directional episode")
    mix = np.asarray(CFG["adverse_memory_weights"])
    surprise = np.asarray(CFG["surprise_weights"])
    debt_weights = np.asarray(CFG["debt_weights"])
    hold_weights = np.asarray(CFG["hold_weights"])
    rows = []
    prev_time = None
    prev_close = 0.
    debt = shock = 0.
    usual = impact = np.nan
    for ts, close, scale, effort, raw in zip(bars.index, bars.close, activation.scale,
                                              activation.effort, activation.reservoir, strict=True):
        if prev_time is None or ts - prev_time != pd.Timedelta(minutes=1):
            prev_close = close
            debt = shock = 0.
            usual = impact = np.nan
        change = side * (close - prev_close)
        adverse = max(0., -change) / scale
        v = CFG["volume_base"] ** effort if with_volume else CFG["price_control_volume"]
        debt = max(0., debt_weights @ [debt, shock, max(0.,change)])
        shock = 0.
        if adverse > 0:
            if np.isfinite(usual):
                excess = np.maximum(0., surprise @ [adverse, usual, v*impact] + CFG["surprise_bias"])
                shock = scale * min(excess)
                usual = mix @ [usual, adverse]
                impact = mix @ [impact, adverse/v]
            else:
                usual, impact = adverse, adverse/v
        hold = hold_weights @ [side*raw, debt]
        rows.append((hold, debt, shock, usual, impact))
        prev_close, prev_time = close, ts
    return pd.DataFrame(rows,index=bars.index,columns=["hold","debt","pending_shock","usual_move","usual_impact"])
