"""Online associative memory of the intersection of executable displacements."""
import numpy as np
import pandas as pd

BLOCK = 8
WARM_MASS = 4
DECAY = 15 / 16
HURDLE = 3  # points: one MNQ round trip under stress


def encode(bars):
    # Rows of memory index the rank of the middle of three consecutive closes
    # after reflecting the path to orient its most recent displacement upward.
    mass = np.zeros(3)
    value = np.zeros(3)
    mid = np.zeros(3)
    pending = []
    rows = []
    held = np.zeros(3)
    close = bars.close.to_numpy()
    op = bars.open.to_numpy()
    for i, t in enumerate(bars.index):
        if i == 0 or t - bars.index[i - 1] != pd.Timedelta(minutes=1):
            pending.clear()
            held[:] = 0
            start = i
        for decision, cell, sign in pending[:]:
            if i == decision + BLOCK + 2:
                # Matched shifts of entry AND exit. A straddling interval
                # contributes zero. Midpoint ablation retains average payoff.
                a, b = (sign * (op[i - 1] - op[decision + 1]),
                        sign * (op[i] - op[decision + 2]))
                robust = max(0, min(a, b)) + min(0, max(a, b))
                mass[cell] = DECAY * mass[cell] + 1
                value[cell] = DECAY * value[cell] + robust
                mid[cell] = DECAY * mid[cell] + (a + b) / 2
                pending.remove((decision, cell, sign))
        minute = t.hour * 60 + t.minute - 570
        cell, sign = -1, 0
        forecasts = np.zeros(3)
        if minute % BLOCK == 0:
            held[:] = 0
            if i - start >= 2 * BLOCK and minute + BLOCK + 2 < 385:
                x, y, z = close[[i - 2 * BLOCK, i - BLOCK, i]]
                sign = np.sign(z - y)
                if sign and x != y and x != z:
                    # In reflected coordinates y < z: x lies left, inside, or right.
                    cell = int(sign * (x - y) > 0) + int(sign * (x - z) > 0)
                    pending.append((i, cell, sign))
                    forecasts = sign * np.array([value[cell] / (WARM_MASS + mass[cell]),
                                                 mid[cell] / (WARM_MASS + mass[cell]),
                                                 value.sum() / (3 * WARM_MASS + mass.sum())])
                    held = np.where(abs(forecasts) > HURDLE, 2 * np.sign(forecasts), 0)
        rows.append((cell, sign, *mass, *forecasts, *held))
    return pd.DataFrame(rows, index=bars.index, columns=[
        'cell', 'orientation', 'mass0', 'mass1', 'mass2', 'intersection_points',
        'midpoint_points', 'pooled_points', 'intersection', 'midpoint', 'pooled'])
