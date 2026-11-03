"""Causal 32-minute price/volume path for self-supervised representation learning."""
from __future__ import annotations

import numpy as np
import pandas as pd

PATH_RETURNS = 32
PATH_VOLUMES = 32
PATH_WIDTH = PATH_RETURNS + PATH_VOLUMES


def completed_path(bars: pd.DataFrame, atr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Use 33 past/current closes and 32 past/current volumes, never future bars."""
    if atr.shape != (len(bars),):
        raise ValueError("Aligned causal ATR required")
    n = len(bars)
    matrix = np.full((n, PATH_WIDTH), np.nan)
    ready = np.zeros(n, dtype=bool)
    close = bars.close.to_numpy(float)
    volume = bars.volume.to_numpy(float)
    segment = bars.segment.to_numpy()
    if not np.isfinite(close).all() or not np.isfinite(volume).all() or (volume < 0).any():
        raise ValueError("Finite nonnegative completed candles required")
    for i in range(PATH_RETURNS, n):
        if segment[i - PATH_RETURNS] != segment[i] or not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        returns = np.diff(close[i - PATH_RETURNS:i + 1]) / atr[i]
        log_volume = np.log1p(volume[i - PATH_VOLUMES + 1:i + 1])
        matrix[i] = np.r_[returns, log_volume - log_volume.mean()]
        ready[i] = True
    return matrix, ready
