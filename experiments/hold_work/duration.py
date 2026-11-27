"""Fixed positive-kernel recurrent memory for parent-exit duration."""
from math import expm1, log, log1p


class Duration:
    def __init__(self):
        self.count = self.sum_x = self.sum_log = self.sum_xlog = 0.0

    @staticmethod
    def coordinate(h):
        return 2.0 * (h - 1.0) / (h + 1.0) - 1.0

    def predict(self, h, clock):
        x = self.coordinate(h)
        def read(query):
            mass = 16.0 + self.count + query*self.sum_x
            reward = 16.0*log(5.0) + self.sum_log + query*self.sum_xlog
            return min(clock, max(1.0, expm1(reward/mass)))
        return {'unconditional': read(0.0), 'conditioned': read(x)}

    def observe(self, h, actual):
        x = self.coordinate(h)
        logged = log1p(actual)
        self.count += 1.0
        self.sum_x += x
        self.sum_log += logged
        self.sum_xlog += x*logged
