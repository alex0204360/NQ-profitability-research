"""Frozen position-relative evidence against remaining in a reservoir trade."""
from pathlib import Path
import json
import math
import numpy as np

W = json.loads(Path(__file__).with_name("weights.json").read_text())


def inputs(bars):
    """Bar body in lagged range units and prior volume odds; reset at gaps."""
    result = []
    previous = None
    retain = W["range_volume_retention"]
    for b in bars.itertuples():
        width = max(W["tick"], b.high - b.low)
        if previous is None or (b.Index - previous).total_seconds() != 60:
            average_range, average_volume, last_volume = width, b.volume, b.volume
            body, odds = 0., 1.
        else:
            body = float(np.clip((b.close - b.open) / average_range, -1, 1))
            odds = (last_volume + 1) / (average_volume + 1)
        result.append((body, odds, average_range))
        average_range = retain * average_range + (1 - retain) * width
        average_volume = retain * average_volume + (1 - retain) * b.volume
        previous, last_volume = b.Index, b.volume
    return result


class ExitHead:
    def __init__(self, rows, volume):
        self.rows = rows
        self.volume = volume
        self.fractions = np.array(W["fractions"])
        self.wealth = np.ones(len(self.fractions))
        self.activations = []

    def close_scores(self, i, close, raw, position, exited, contiguous, long, short):
        if position is None:
            self.wealth.fill(1.)
            return raw, math.nan
        body, odds, scale = self.rows[i]
        side = position["side"]
        q = odds if self.volume else 1.
        adjusted = self.fractions * q
        stake = adjusted / (1 - self.fractions + adjusted)
        self.wealth *= 1 - side * body * stake
        evidence = float(np.dot(W["mixture"], self.wealth))
        self.activations.append((i, side, evidence, *self.wealth))
        margin = scale * math.log2(W["evidence_boundary"] / evidence)
        return raw, min(side * raw, margin)
