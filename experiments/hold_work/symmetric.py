"""Causal counterfactual pulse for the frozen recovered-distance circuit."""
from .circuit import Head


class SymmetricHead(Head):
    def step(self, open_, high, low, close, volume, prior_mean_volume):
        # Evaluate the two possible directions of the just-observed magnitude,
        # using the same pre-bar memory for both branches.
        move = self.direction * (close - self.entry) - self.last
        magnitude = abs(move)
        gap = self.peak - self.last
        up = magnitude - 0.5 * min(magnitude, gap)
        down = -magnitude - 0.5 * min(magnitude, self.repair)
        neutral = (up + down) / 2
        state = super().step(open_, high, low, close, volume, prior_mean_volume)
        self.price -= neutral
        self.volume -= state["participation"] * neutral
        state.update(price=self.price, volume=self.volume,
                     neutral_pulse=neutral, centered_pulse=state["evidence"] - neutral)
        return state
