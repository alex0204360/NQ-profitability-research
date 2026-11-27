import itertools
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from experiments.capacity import neuron


class CounterfactualNeuronTests(unittest.TestCase):
    def test_zero_charge_reachable_interval_and_neutral_decay(self):
        a, forecast, stock, steps = neuron.A, 0.4, 1.2, 4
        lower = a ** steps * (forecast - stock)
        upper = a ** steps * (forecast + stock)

        # The frozen zero-new-charge recurrence across a bounded motion grid.
        grid = (-1.0, -0.5, 0.0, 0.5, 1.0)
        terminals = []
        for path in itertools.product(grid, repeat=steps):
            f, s = forecast, stock
            for motion in path:
                motion = min(1.0, max(-1.0, motion))
                f, s = a * (f + s * motion), a * s * (1.0 - abs(motion))
            terminals.append(f)
        self.assertTrue(all(lower - 1e-12 <= value <= upper + 1e-12
                            for value in terminals))

        neutral = forecast
        for _ in range(steps):
            neutral = a * neutral
        self.assertAlmostEqual(neutral, a ** steps * forecast)
        self.assertGreater(neutral, 0.0)  # Decay alone cannot reverse a positive sign.

        # Releasing all stock immediately attains either endpoint; then wait neutrally.
        for sign, endpoint in ((-1.0, lower), (1.0, upper)):
            f, s = forecast, stock
            f, s = a * (f + s * sign), a * s * (1.0 - abs(sign))
            for _ in range(steps - 1):
                f, s = a * (f + s * 0.0), a * s
            self.assertAlmostEqual(f, endpoint)

    def test_price_charge_matches_uniform_quadrature(self):
        # Midpoint integration of E[max(0, U-|m|)] for U uniform[-1, 1].
        n = 200_000
        u = -1.0 + (np.arange(n) + 0.5) * (2.0 / n)
        for motion in (0.0, 0.2, -0.2, 0.6, -0.6, 0.95, -0.95):
            numeric = np.maximum(0.0, u - abs(motion)).mean()
            self.assertAlmostEqual(neuron.price_charge(motion), numeric, delta=1e-5)

    def test_price_charge_is_sign_invariant_and_zero_at_extremes(self):
        for motion in np.linspace(0.0, 1.0, 21):
            self.assertEqual(neuron.price_charge(motion),
                             neuron.price_charge(-motion))
        for motion in (-2.0, -1.0, 1.0, 2.0):
            self.assertEqual(neuron.price_charge(motion), 0.0)
        self.assertEqual(neuron.price_charge(0.0), 0.25)

    def test_warmup_and_gap_reset_drop_old_price_memory(self):
        rows = pd.DataFrame([
            # First available warmup bar: no old forecast or stock is inherited.
            {"age": 1, "motion": 0.0, "scale": 2.0, "reservoir": np.nan, "stock": 0.0},
            {"age": 2, "motion": 0.0, "scale": 2.0, "reservoir": 3.0, "stock": 0.5},
            # A new age-1 segment represents a gap/session reset.
            {"age": 1, "motion": 0.0, "scale": 4.0, "reservoir": np.nan, "stock": 0.0},
            {"age": 2, "motion": 0.0, "scale": 4.0, "reservoir": 2.0, "stock": 0.25},
        ])
        with patch.object(neuron, "activations", side_effect=lambda bars, _mode: bars.copy()):
            encoded = neuron.encode(rows)
        self.assertAlmostEqual(encoded.loc[0, "price_stock"], neuron.price_charge(0.0))
        self.assertTrue(np.isnan(encoded.loc[0, "price_forecast"]))
        self.assertAlmostEqual(encoded.loc[2, "price_stock"], neuron.price_charge(0.0))
        self.assertAlmostEqual(encoded.loc[3, "price_stock"],
                               neuron.A * neuron.price_charge(0.0) + neuron.price_charge(0.0))
        # New charge is stored on the age-1 bar, not released into forecast then.
        self.assertAlmostEqual(encoded.loc[3, "price_forecast"], 0.0)
        self.assertAlmostEqual(encoded.loc[3, "price_long"],
                               neuron.A * (-neuron.SHOCK * 4.0 * encoded.loc[3, "price_stock"]))

    def test_prefix_outputs_do_not_depend_on_future_rows(self):
        rows = pd.DataFrame([
            {"age": 1, "motion": 0.25, "scale": 2.0, "reservoir": 1.0, "stock": 0.2},
            {"age": 2, "motion": -0.5, "scale": 2.5, "reservoir": 0.5, "stock": 0.3},
            {"age": 3, "motion": 1.5, "scale": 3.0, "reservoir": 2.0, "stock": 0.25},
            {"age": 4, "motion": -1.5, "scale": 1.5, "reservoir": -1.0, "stock": 0.4},
        ])
        with patch.object(neuron, "activations", side_effect=lambda bars, _mode: bars.copy()):
            prefix = neuron.encode(rows.iloc[:2])
            extended = neuron.encode(rows)
        pd.testing.assert_frame_equal(prefix, extended.iloc[:2])


if __name__ == "__main__":
    unittest.main()
