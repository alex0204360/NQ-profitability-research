"""Position-relative, close-updated holding-value hypothesis. Prices in index points."""
import math


class Head:
    def __init__(self, direction, entry_price, scale_at_entry):
        if direction not in (-1, 1) or not math.isfinite(entry_price):
            raise ValueError("invalid entry")
        if not math.isfinite(scale_at_entry) or scale_at_entry <= 0:
            raise ValueError("invalid entry scale")
        self.direction = direction
        self.entry = entry_price
        self.scale = max(0.25, scale_at_entry)
        self.last = self.peak = self.repair = 0.0
        # Net distance initially has a one-range favorable prior.
        self.price = self.volume = self.scale

    def step(self, open_, high, low, close, volume, prior_mean_volume):
        x = self.direction * (close - self.entry)
        advance = max(0.0, x - self.last)
        retreat = max(0.0, self.last - x)
        extension = max(0.0, x - self.peak)
        restored = advance - extension
        # Re-losing a previously recovered point cancels its provisional credit.
        erased = min(retreat, self.repair)
        self.repair = 0.0 if x >= self.peak else self.repair + restored - erased
        self.peak = max(self.peak, x)
        evidence = extension + 0.5 * restored - retreat - 0.5 * erased
        # At normal mass the paired cells agree exactly. A busy flat bar
        # discounts both memories identically and contributes no directional vote.
        participation = (2.0 * volume + 2.0) / (volume + prior_mean_volume + 2.0)
        self.price = 0.75 * self.price + evidence
        self.volume = 0.75 * self.volume + participation * evidence
        self.last = x
        eligible = self.peak >= self.scale
        return dict(price=self.price, volume=self.volume, eligible=eligible,
                    trail=x - self.peak + 2 * self.scale if eligible else self.scale,
                    extension=extension, restored=restored, erased=erased,
                    evidence=evidence, participation=participation, peak=self.peak,
                    repair=self.repair, displacement=x)
