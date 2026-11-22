"""Single-deletion price paths. No estimated coefficients or outcome memory."""
import numpy as np
import pandas as pd

from neuron import BLOCK, HURDLE


def encode(bars):
    close = bars.close.to_numpy()
    held = np.zeros(3)
    rows = []
    for i, t in enumerate(bars.index):
        if i == 0 or t - bars.index[i-1] != pd.Timedelta(minutes=1):
            start = i
            held[:] = 0
        minute = t.hour * 60 + t.minute - 570
        cell = -1
        sign = 0
        delta = residual = extreme = 0.
        scores = np.zeros(3)
        if minute % BLOCK == 0:
            held[:] = 0
            if i-start >= BLOCK and minute + BLOCK + 2 < 385:
                path = np.diff(close[i-BLOCK:i+1])
                delta = path.sum()
                sign = np.sign(delta)
                extreme = path[np.argmax(sign * path)]
                residual = delta - extreme
                # The others must have collectively walked in the opposite direction.
                cell = int(sign * residual < 0)
                # Forecast a retracement only up to the lesser of the observed
                # displacement and the opposing displacement after deletion.
                amount = min(abs(delta), abs(residual))
                scores = np.array([-sign * amount * cell, -delta,
                                   -sign * amount * (1-cell)])
                held = np.where(abs(scores) > HURDLE, 2 * np.sign(scores), 0.)
        rows.append((cell, sign, delta, extreme, residual, *scores, *held))
    return pd.DataFrame(rows, index=bars.index, columns=[
        'cell','orientation','delta','extreme','residual','erase_points',
        'fade_points','distributed_points','erase','fade','distributed'])
