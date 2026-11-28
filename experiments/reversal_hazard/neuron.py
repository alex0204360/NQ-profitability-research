"""Prior-session survival memory for the next reservoir-sign transition."""
import numpy as np

GRID = np.arange(17) / 16.0
PRIOR = 20.0


class Hazard:
    def __init__(self):
        self.n = self.reversals = self.possible = 0
        self.exceedances = np.zeros(len(GRID), dtype=np.int64)

    def predict(self, ratio):
        ratio = np.asarray(ratio, dtype=float)
        if np.isnan(ratio).any() or (ratio < 0).any():
            raise ValueError('distance must be nonnegative, or infinite for zero stock')
        possible = ratio <= 1.0
        prior = 0.5 * np.exp(-2.0 * GRID)
        tail = (self.exceedances + PRIOR * prior) / (self.n + PRIOR)
        return {
            'constant': np.full(ratio.shape, (self.reversals + PRIOR/16) / (self.n + PRIOR)),
            'feasibility': np.where(possible, (self.reversals + PRIOR/4) / (self.possible + PRIOR), 0.),
            'laplace': np.where(possible, 0.5*np.exp(-2*ratio), 0.),
            'grid': np.where(possible, np.interp(ratio, GRID, tail), 0.),
        }

    def settle_session(self, adverse, possible, reversed_sign):
        adverse = np.asarray(adverse,dtype=float)
        possible = np.asarray(possible,dtype=bool)
        reversed_sign = np.asarray(reversed_sign,dtype=bool)
        if not (adverse.shape == possible.shape == reversed_sign.shape and np.isfinite(adverse).all()):
            raise ValueError('incomplete session outcomes')
        if np.any(reversed_sign & ~possible):
            raise ValueError('observed impossible reversal')
        self.n += len(adverse)
        self.reversals += int(reversed_sign.sum())
        self.possible += int(possible.sum())
        self.exceedances += (adverse[:,None] >= GRID).sum(axis=0)
