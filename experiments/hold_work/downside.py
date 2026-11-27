"""Frozen forecast roughness, causal scale transformation, and tail memory."""
from bisect import insort
from math import ceil, sqrt


def scales(entry_range, forecast, roughness, minutes_left):
    remaining = max(1, minutes_left)
    distance = abs(forecast)
    steps = 1.0 if roughness is None else max(1.0, distance / max(0.25, roughness))
    duration_root = min(sqrt(remaining), steps)
    return {'constant': 1.0, 'range': entry_range, 'clock': entry_range * sqrt(remaining),
            'distance': entry_range * duration_root}


class TailMemory:
    def __init__(self):
        self.history = {name: [] for name in ('constant', 'range', 'clock', 'distance')}

    @property
    def count(self):
        return len(self.history['constant'])

    def predict(self, scale):
        if self.count < 20:
            return None
        index = ceil(0.8 * self.count) - 1
        return {name: scale[name] * history[index] for name, history in self.history.items()}

    def observe(self, scale, loss):
        for name, history in self.history.items():
            insort(history, loss / scale[name])
