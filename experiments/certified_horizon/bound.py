"""Integer horizon in the continuous input space of the frozen reservoir."""
from math import isfinite

DECAY = 7 / 8


def earliest_flip(forecast, stock):
    """Return earliest neutral/opposite close for a nonzero normalized forecast."""
    if not (isfinite(forecast) and forecast != 0 and isfinite(stock) and stock >= 0):
        raise ValueError("expected a finite nonzero forecast and finite nonnegative stock")
    deficit = abs(forecast) - stock
    horizon = 1
    while deficit > 0:
        deficit = DECAY * deficit - 1.
        horizon += 1
    return horizon
