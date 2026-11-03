"""Past-only signal hysteresis and uncertainty-aware drift/diffusion filter."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

WINDOW_CLOSES = 32
RETURNS = WINDOW_CLOSES - 1
HORIZON = 10
STRESS_COST_POINTS = 3.0  # $6 round trip / $2 per MNQ index point
PROBABILITY_GATE = .60


def diffusion_probability(bars: pd.DataFrame, side: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Approximate P(gross directional ten-bar move > stressed costs)."""
    n = len(bars)
    if side.shape != (n,) or not np.isin(side, [-1, 0, 1]).all():
        raise ValueError("Aligned directional gate signals required")
    close = bars.close.to_numpy(float)
    segment = bars.segment.to_numpy()
    probability = np.full(n, np.nan)
    drift = np.full(n, np.nan)
    sigma = np.full(n, np.nan)
    for i in np.flatnonzero(side):
        if i < RETURNS or segment[i - RETURNS] != segment[i]:
            continue
        observed = np.diff(close[i - RETURNS:i + 1])
        mu = float(observed.mean())
        s = float(observed.std(ddof=1))
        if not np.isfinite(mu) or not np.isfinite(s) or s <= 0:
            continue
        forecast_std = s * np.sqrt(HORIZON + HORIZON**2 / RETURNS)
        probability[i] = float(norm.cdf((side[i] * HORIZON * mu - STRESS_COST_POINTS) / forecast_std))
        drift[i] = mu
        sigma[i] = s
    return probability, drift, sigma


def filtered_signals(gate: np.ndarray, probability: np.ndarray,
                     segments: np.ndarray) -> dict[str, np.ndarray]:
    if gate.shape != probability.shape or segments.shape != gate.shape:
        raise ValueError("Aligned signals, probabilities, and segments required")
    if not np.isin(gate, [-1, 0, 1]).all():
        raise ValueError("Invalid frozen gate signal")
    persistence = np.zeros(len(gate), dtype=bool)
    persistence[1:] = ((gate[1:] != 0) & (gate[1:] == gate[:-1]) &
                       (segments[1:] == segments[:-1]))
    diffusion = (gate != 0) & np.isfinite(probability) & (probability > PROBABILITY_GATE)
    return {"unchanged_8_gate": gate.copy(),
            "persistent_2bar": np.where(persistence, gate, 0).astype(int),
            "diffusion_p60": np.where(diffusion, gate, 0).astype(int),
            "persistent_and_diffusion": np.where(persistence & diffusion, gate, 0).astype(int)}
