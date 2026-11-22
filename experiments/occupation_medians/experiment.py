"""Exact multiplicative recurrent cells. Inputs are consecutive completed bars."""
from math import isclose
from itertools import product


class OrderCell:
    def __init__(self):
        self.p = self.q = self.area = self.clock = self.mass = 0
        self.n = 0

    def step(self, displacement, volume):
        if volume < 0:
            raise ValueError("negative volume")
        self.area += self.p * volume - self.q * displacement
        self.clock += self.p - self.n * displacement
        self.mass += abs(displacement)
        self.p += displacement
        self.q += volume
        self.n += 1
        raw = self.area / (self.mass * self.q) if self.mass * self.q else 0
        corrected = raw - self.clock / (self.n * self.mass) if self.mass * self.q else 0
        return raw, corrected


def trace(path, volumes):
    cell = OrderCell()
    return [cell.step(x, v) for x, v in zip(path, volumes, strict=True)]


if __name__ == "__main__":
    path = (2, 1, -1, 0)
    for volumes in [(2, 2, 2, 2), (1, 1, 3, 3), (3, 3, 1, 1)]:
        print(volumes, trace(path, volumes))
    cases = 0
    for path in product((-1, 0, 1), repeat=4):
        for volumes in product((1, 2, 3), repeat=4):
            score = trace(path, volumes)[-1][1]
            assert isclose(score, -trace(path[::-1], volumes[::-1])[-1][1], abs_tol=1e-12)
            assert isclose(score, trace([2*x for x in path], [3*v for v in volumes])[-1][1], abs_tol=1e-12)
            if len(set(volumes)) == 1:
                assert abs(score) < 1e-12
            cases += 1
    print(cases, "paths passed")
