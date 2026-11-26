"""Fixed common-sign entry and asymmetric NQ hold gate."""
import numpy as np


class Agreement:
    def __init__(self, peer, veto):
        self.peer = peer.to_numpy()
        self.veto = veto

    def close_scores(self, i, close, raw, position, exited, contiguous, long, short):
        other = self.peer[i]
        if not np.isfinite(other):
            return 0., float("nan")
        # min is an exact ReLU circuit: min(a,b) = a - ReLU(a-b).
        entry = max(0., min(raw,other)) - max(0., min(-raw,-other))
        if position is None:
            return entry, float("nan")
        side = position["side"]
        hold = side * raw
        if self.veto:
            hold = min(hold, 3. + side * other)
        return entry, hold
