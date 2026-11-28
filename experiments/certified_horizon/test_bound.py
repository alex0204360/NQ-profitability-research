"""Synthetic checks for the integer earliest-sign-flip bound."""
import itertools
import unittest
from pathlib import Path

import numpy as np

from experiments.path_order.brain import weights as frozen_weights
from .bound import earliest_flip


RETENTION = 7.0 / 8.0


def formula_horizon(forecast, stock):
    """Slow direct protocol formula, intentionally independent of bound.py."""
    target = abs(float(forecast))
    reach = float(stock)
    h = 1
    while target > reach:
        h += 1
        reach += RETENTION ** (-(h - 1))
    return h


class EarliestFlipBoundTests(unittest.TestCase):
    def test_boundaries_signed_forecasts_and_zero_stock(self):
        with self.assertRaises(ValueError):
            earliest_flip(0.0, 0.0)
        self.assertEqual(earliest_flip(0.75, 1.25), 1)
        self.assertEqual(earliest_flip(-0.75, 1.25), 1)
        self.assertEqual(earliest_flip(1.0, 0.0), 2)
        self.assertEqual(earliest_flip(-2.0, 0.0), 3)
        self.assertEqual(earliest_flip(2.0, 0.0), 3)
        self.assertEqual(earliest_flip(1.0e6, 0.0), formula_horizon(1.0e6, 0.0))

    def test_each_exact_reachability_boundary_and_just_above(self):
        stock = 0.375
        reach = stock
        for h in range(1, 8):
            if h > 1:
                reach += RETENTION ** (-(h - 1))
            self.assertEqual(earliest_flip(reach, stock), h)
            self.assertEqual(earliest_flip(-reach, stock), h)
            above = np.nextafter(reach, np.inf)
            self.assertEqual(earliest_flip(above, stock), h + 1)

    def test_original_frozen_weights_realize_flat_charge_then_adverse_release_witness(self):
        cfg = frozen_weights("reservoir")
        state = np.asarray(cfg["state"], dtype=float)
        self.assertAlmostEqual(state[0, 0], RETENTION)
        self.assertAlmostEqual(state[1, 1], RETENTION)
        self.assertAlmostEqual(state[1, 2], RETENTION)
        rectifier = np.asarray(cfg["rectifier"], dtype=float)
        bias = np.asarray(cfg["rectifier_bias"], dtype=float)
        charge = np.asarray(cfg["charge"], dtype=float)
        routing = np.asarray(cfg["routing"], dtype=float)

        def frozen_step(forecast, stock, effort, motion):
            hinges = np.maximum(0.0, rectifier @ np.array([effort, motion]) + bias)
            q = max(0.0, float(charge @ np.r_[effort, hinges[:2]]))
            features = np.r_[1.0, max(motion, 0.0), max(-motion, 0.0), hinges[2:]]
            retained, signed = stock * (routing @ features)
            stock_next, forecast_next = state @ np.array([retained, signed, forecast, q])
            return float(forecast_next), float(stock_next), q

        # The extremal prefix uses maximal new charge at flat motion; the final
        # saturated adverse motion releases stock and carries no new charge.
        self.assertEqual(frozen_step(1.0, 0.25, 1.0, 0.0)[2], 1.0)
        self.assertEqual(frozen_step(1.0, 0.25, 0.0, -1.0)[2], 0.0)
        for h in range(1, 7):
            stock = 0.25
            boundary = stock + sum(RETENTION ** (-j) for j in range(1, h))
            forecast = boundary
            current_stock = stock
            for _ in range(h - 1):
                forecast, current_stock, q = frozen_step(forecast, current_stock, 1.0, 0.0)
                self.assertEqual(q, 1.0)
                self.assertGreater(forecast, 0.0)
            # The final adverse saturated release is the first possible sign flip.
            forecast, current_stock, q = frozen_step(forecast, current_stock, 0.0, -1.0)
            self.assertEqual(q, 0.0)
            self.assertAlmostEqual(forecast, 0.0, places=12)
            self.assertEqual(earliest_flip(boundary, stock), h)

    def test_finite_exhaustive_short_path_recurrences_respect_the_bound(self):
        # Enumerate bounded categorical encoder choices. For positive motion the
        # stock penalty is maximized; charge is independently bounded by one.
        motions = (-1.0, 0.0, 1.0)
        cfg = frozen_weights("reservoir")
        valid_actions = tuple((motion, effort) for motion in motions
                              for effort in (0.0, 1.0))
        for steps in range(2, 5):
            for forecast in (0.5, 1.25, 2.0, 3.5):
                stock = 0.75
                h = earliest_flip(forecast, stock)
                for path in itertools.product(valid_actions, repeat=steps):
                    signed_forecast, current_stock = forecast, stock
                    flipped_at = None
                    for t, (motion, effort) in enumerate(path, start=1):
                        hinges = np.maximum(0.0, np.asarray(cfg["rectifier"]) @
                                            np.array([effort, motion]) + np.asarray(cfg["rectifier_bias"]))
                        charge = max(0.0, float(np.asarray(cfg["charge"]) @ np.r_[effort, hinges[:2]]))
                        features = np.r_[1.0, max(motion, 0.0), max(-motion, 0.0), hinges[2:]]
                        retained, signed_release = current_stock * (np.asarray(cfg["routing"]) @ features)
                        current_stock, signed_forecast = np.asarray(cfg["state"]) @ np.array(
                            [retained, signed_release, signed_forecast, charge])
                        if signed_forecast <= 0:
                            flipped_at = t
                            break
                    if flipped_at is not None:
                        self.assertGreaterEqual(flipped_at, h)

    def test_small_grid_agrees_with_direct_integer_recurrence(self):
        for forecast in np.linspace(-40.0, 40.0, 161):
            for stock in (0.0, 0.01, 0.5, 2.0, 15.0):
                if forecast == 0:
                    with self.assertRaises(ValueError):
                        earliest_flip(forecast, stock)
                    continue
                self.assertEqual(earliest_flip(forecast, stock),
                                 formula_horizon(forecast, stock))


if __name__ == "__main__":
    unittest.main()
