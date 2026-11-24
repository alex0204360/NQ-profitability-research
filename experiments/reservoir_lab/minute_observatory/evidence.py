"""Erase the strongest still-live supporting release before admitting an entry."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

WEIGHTS = json.loads(Path(__file__).with_name("weights.json").read_text())


def evidence(a):
    decay = WEIGHTS["decay"]
    orient = np.array(WEIGHTS["sided_input"]).ravel()
    readout = np.array(WEIGHTS["entry_readout"])
    peak = np.zeros(2)
    rows = []
    for row in a.itertuples():
        if row.age == 1:
            peak.fill(0.)
        peak = decay * np.maximum(peak, np.maximum(0., orient * row.signed_release))
        long, short = readout @ [row.reservoir, *(row.scale * peak)]
        entry = max(0.,long) - max(0.,short) if np.isfinite(long) else np.nan
        rows.append((*peak,entry))
    return pd.DataFrame(rows,index=a.index,columns=["peak_long","peak_short","corroborated"])


class EntryOnly:
    def __init__(self, entry):
        self.entry = entry.to_numpy()

    def close_scores(self, i, close, raw, position, exited, contiguous, long_hold, short_hold):
        return self.entry[i], abs(raw)
