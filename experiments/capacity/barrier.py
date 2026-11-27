"""Exact next contiguous parent-sign reversal barrier in MNQ price points."""
import numpy as np
import pandas as pd

from .neuron import A


def audit(bars, encoded):
    z = encoded
    sign = np.sign(z.reservoir)
    # Encoder scales use a lagged EMA with alpha 1/32. After reset, the
    # first spread may be below the tick; encodable forecasts require 32 bars.
    # Track the unclamped width to preserve the exact recurrence.
    widths = []
    previous = None
    for b in bars.itertuples():
        spread = b.high - b.low
        if previous is None or b.Index - previous != pd.Timedelta(minutes=1):
            width = max(.25, spread)
        width = width*31/32 + spread/32
        widths.append(max(.25, width))
        previous = b.Index
    scale_next = pd.Series(widths, index=z.index)
    ratio = (z.reservoir / z.scale).abs()/z.stock.replace(0, np.nan)
    same = z.index.to_series().shift(-1)-z.index.to_series() == pd.Timedelta(minutes=1)
    valid = same & z.reservoir.notna() & z.reservoir.shift(-1).notna() & sign.ne(0)
    possible = ratio.le(1) & ratio.notna()
    required_move = (scale_next*ratio).where(possible)
    motion = (bars.close.shift(-1)-bars.close)/scale_next
    implied_next = A*(z.reservoir / z.scale + z.stock*motion.clip(-1,1))*scale_next
    if not np.allclose(implied_next[valid], z.reservoir.shift(-1)[valid], atol=1e-10,rtol=1e-12):
        raise AssertionError('one-step counterfactual must reproduce the parent')
    actual_reversal = sign*z.reservoir.shift(-1) <= 0
    threshold = bars.close - sign*required_move
    crossed = sign*(bars.close.shift(-1)-threshold) <= 0
    near = (bars.close.shift(-1)-threshold).abs() < 1e-9
    if ((crossed!=actual_reversal) & valid & ~near).any():
        raise AssertionError('close barrier disagrees with parent sign')
    adverse_extreme = bars.low.shift(-1).where(sign.gt(0), bars.high.shift(-1))
    touched = (sign*(adverse_extreme-threshold)<=0) & possible
    return pd.DataFrame(dict(issued_bar=z.index, direction=sign, forecast=z.reservoir,
                             stock=z.stock, range_next=scale_next, required_ratio=ratio,
                             next_close_barrier=threshold, reachable=possible,
                             touched_intrabar=touched, closed_through=actual_reversal,
                             near_boundary=near)).loc[valid].reset_index(drop=True)
