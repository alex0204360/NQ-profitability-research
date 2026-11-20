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
