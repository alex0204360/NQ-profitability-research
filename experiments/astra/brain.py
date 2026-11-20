"""Four-minute signed continuation forecast in NQ points, from completed bars."""
import numpy as np

def forecast(g):
    h,l,c = g.high,g.low,g.close
    scale = (h-l).rolling(14).mean().shift(2).replace(0,np.nan)
    # Detect acceptance outside a preceding six-minute auction.
    ceiling=h.shift(2).rolling(6).max()
    floor=l.shift(2).rolling(6).min()
    def evidence(direction, boundary):
        clearance=direction*(c-boundary)/scale
        # Two closes across a boundary provide stronger evidence than one.
        held=direction*(c.shift()-boundary)/scale
        progress=direction*(c-c.shift(4))/scale
        travel=c.diff().abs().rolling(4).sum()/scale
        wick=((h-c) if direction==1 else (c-l))/scale
        return (0.55*clearance.clip(-2,2)+0.45*held.clip(-2,2)
                +0.30*progress.clip(-3,3)-0.22*travel.clip(0,5)
                -0.70*wick.clip(0,2)-0.85).clip(lower=0)
    return scale*(evidence(1,ceiling)-evidence(-1,floor))

def compression_forecast(g):
    """Require a breakout from contracting auctions, before the breakout starts."""
    width=g.high-g.low
    recent=width.shift(2).rolling(4).mean()
    earlier=width.shift(6).rolling(10).mean()
    # At 2/3 of prior width, pass the original forecast at full strength.
    # Equal or expanding width means no stored compression.
    gate=(3*(1-recent/earlier.replace(0,np.nan))).clip(0,1)
    return forecast(g)*gate
