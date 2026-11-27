"""Chronological holding-value estimates from previously resolved trades."""
import math


class Memory:
    def __init__(self):
        self.mass = [0.0] * 4
        self.value = [0.0] * 4

    @staticmethod
    def features(scale, price_score, volume_score):
        if not (math.isfinite(scale) and scale >= 0.25
                and math.isfinite(price_score) and math.isfinite(volume_score)):
            raise ValueError("expected a positive entry range and finite causal scores")
        a = math.tanh(price_score / scale - 1.0)
        b = math.tanh((volume_score - price_score) / scale)
        return (1.0, a, b, a * b)

    def predict(self, scale, price_score, volume_score):
        u = self.features(scale, price_score, volume_score)
        out = {}
        for name, dimension in (("constant", 1), ("price", 2), ("interaction", 4)):
            support = sum(u[i] * self.mass[i] for i in range(dimension))
            total = sum(u[i] * self.value[i] for i in range(dimension))
            out[name] = scale * total / (16.0 + support)
        return out

    def observe(self, scale, price_score, volume_score, realized_pts):
        if not math.isfinite(realized_pts):
            raise ValueError("update requires a mature, finite holding-value label")
        u = self.features(scale, price_score, volume_score)
        rate = realized_pts / scale
        for i, element in enumerate(u):
            self.mass[i] += element
            self.value[i] += element * rate
