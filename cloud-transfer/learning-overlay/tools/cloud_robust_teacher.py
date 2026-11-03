"""Build execution-aware teaching targets from fully matured, contiguous bars.

These are hindsight labels for training only. A live student receives causal
completed-bar features, never these targets or future bars.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from tools.cloud_campaign01 import targets


def robust_teacher(bars: pd.DataFrame, maturity_cutoff: pd.Timestamp,
                   stress_round_trip_usd: float = 6.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return [long, short] net under both fills, validity, and hindsight class.

    Values have shape (bar, action, fill_delay). An action class is 0 unless its
    *worst* fill timing was positive. Keep every eligible losing alternative as
    a training target; never fit only the hindsight winners.
    """
    if not np.isfinite(stress_round_trip_usd) or stress_round_trip_usd < 0:
        raise ValueError("Invalid stress round-trip cost")
    gross, valid = targets(bars, maturity_cutoff)
    net = np.stack((gross - stress_round_trip_usd,
                    -gross - stress_round_trip_usd), axis=1)
    net[~valid] = np.nan
    worst = np.min(net, axis=2)
    winner = np.zeros(len(bars), dtype=np.int8)
    long_wins = valid & (worst[:, 0] > np.maximum(0, worst[:, 1]))
    short_wins = valid & (worst[:, 1] > np.maximum(0, worst[:, 0]))
    winner[long_wins] = 1
    winner[short_wins] = -1
    return net, valid, winner
