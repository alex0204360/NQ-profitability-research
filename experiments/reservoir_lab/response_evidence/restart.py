"""Change-point variant: propagate the best adverse run since any held close."""
import numpy as np
from exit_head import ExitHead


class RestartHead(ExitHead):
    def close_scores(self, i, close, raw, position, exited, contiguous, long, short):
        # max(1, wealth) is exactly 1 + ReLU(wealth-1). It admits a new
        # change point before the next increment, without reading that increment.
        self.wealth = np.maximum(1., self.wealth)
        return super().close_scores(i, close, raw, position, exited, contiguous, long, short)
