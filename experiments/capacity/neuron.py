"""Frozen signed support margins for the original reservoir and its price sibling."""
import numpy as np

from experiments.path_order.brain import activations

A = 7 / 8
SHOCK = 0.5


def price_charge(motion):
    """Expected positive effort surplus for U uniform on [-1,1] at fixed motion."""
    return 0.25 * max(0.0, 1.0 - abs(motion)) ** 2


def encode(bars):
    z = activations(bars, 'reservoir').copy()
    stored = released = 0.0
    stock, forecast = [], []
    for row in z.itertuples():
        if row.age == 1:
            stored = released = 0.0
        movement = min(1.0, max(-1.0, row.motion))
        released = A * (released + stored * movement)
        stored = A * stored * (1.0 - abs(movement)) + price_charge(row.motion)
        stock.append(stored)
        forecast.append(released * row.scale)
    z['price_stock'] = stock
    z['price_forecast'] = np.where(z.reservoir.notna(), forecast, np.nan)
    for family, f, s in [('hold','reservoir','stock'),('price','price_forecast','price_stock')]:
        for side, sign in [('long',1),('short',-1)]:
            z[family+'_'+side] = A * (sign * z[f] - SHOCK*z.scale*z[s])
    return z
