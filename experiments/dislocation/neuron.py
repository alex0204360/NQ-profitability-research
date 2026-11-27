"""Two price observations and a lagged basis estimate; minute-close inference."""
import pandas as pd


def encode(micro, peer):
    if not micro.index.equals(peer.index):
        raise ValueError('unaligned contracts')
    spread = peer.close - micro.close
    anchor = spread.shift(1).rolling(31, min_periods=31).median()
    def activity(volume):
        return (1+volume) / (1+volume.ewm(span=32,adjust=False).mean().shift(1))
    w_peer = activity(peer.volume)
    share = w_peer/(w_peer + activity(micro.volume))
    residual = spread-anchor
    return pd.DataFrame(dict(basis=anchor, raw_spread=spread, residual=residual, share=share,
                             volume=share*residual, equal=0.5*residual, peer=residual,
                             micro_reversion=(-0.5*micro.close.diff()).where(anchor.notna())))
