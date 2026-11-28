import unittest

import numpy as np

from experiments.reversal_hazard.neuron import GRID, PRIOR, Hazard


class HazardNeuronTests(unittest.TestCase):
    @staticmethod
    def prior_tail(ratio):
        return 0.5 * np.exp(-2.0 * np.asarray(ratio, dtype=float))

    def test_zero_stock_infinite_ratio_is_impossible_exactly(self):
        hazard = Hazard()
        p = hazard.predict(np.array([np.inf]))
        self.assertEqual(p["constant"][0], 1.0 / 16.0)
        for name in ("feasibility", "laplace", "grid"):
            self.assertEqual(p[name][0], 0.0)

    def test_ratio_one_uses_final_cell_and_above_one_is_zero(self):
        hazard = Hazard()
        hazard.n = 16
        hazard.exceedances[:] = np.arange(16, -1, -1, dtype=np.int64)
        p = hazard.predict(np.array([1.0, np.nextafter(1.0, np.inf)]))
        expected_final = (hazard.exceedances[-1] + PRIOR * self.prior_tail(1.0)) / (hazard.n + PRIOR)
        self.assertAlmostEqual(p["grid"][0], expected_final)
        self.assertEqual(p["grid"][1], 0.0)
        self.assertEqual(p["feasibility"][1], 0.0)
        self.assertEqual(p["laplace"][1], 0.0)

    def test_grid_prediction_linearly_interpolates_adjacent_survival_cells(self):
        hazard = Hazard()
        hazard.n = 6
        hazard.exceedances[:] = np.array([6, 5, 4, 3, 3, 2, 2, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0])
        ratio = (5.5 / 16.0)
        p = hazard.predict(np.array([ratio]))["grid"][0]
        tail = (hazard.exceedances + PRIOR * self.prior_tail(GRID)) / (hazard.n + PRIOR)
        expected = (tail[5] + tail[6]) / 2.0
        self.assertAlmostEqual(p, expected)

    def test_prior_counts_and_grid_tail_match_frozen_formulas(self):
        hazard = Hazard()
        ratios = np.array([0.0, 0.5, 1.0, np.inf])
        initial = hazard.predict(ratios)
        self.assertTrue(np.allclose(initial["constant"], 1.0 / 16.0))
        self.assertTrue(np.allclose(initial["feasibility"], [0.25, 0.25, 0.25, 0.0]))
        self.assertTrue(np.allclose(initial["laplace"], [0.5, 0.5*np.exp(-1), 0.5*np.exp(-2), 0.0]))
        expected_grid = np.interp(ratios[:3], GRID, self.prior_tail(GRID))
        self.assertTrue(np.allclose(initial["grid"][:3], expected_grid))
        self.assertEqual(initial["grid"][3], 0.0)

        adverse = np.array([0.1, 0.5, 1.2])
        possible = np.array([True, True, False])
        reversed_sign = np.array([False, True, False])
        hazard.settle_session(adverse, possible, reversed_sign)
        self.assertEqual(hazard.n, 3)
        self.assertEqual(hazard.reversals, 1)
        self.assertEqual(hazard.possible, 2)
        expected_constant = (1 + PRIOR / 16.0) / (3 + PRIOR)
        expected_feasibility = (1 + PRIOR / 4.0) / (2 + PRIOR)
        self.assertAlmostEqual(hazard.predict(np.array([0.5]))["constant"][0], expected_constant)
        self.assertAlmostEqual(hazard.predict(np.array([0.5]))["feasibility"][0], expected_feasibility)
        expected_exceedances = (adverse[:, None] >= GRID).sum(axis=0)
        self.assertTrue(np.array_equal(hazard.exceedances, expected_exceedances))

    def test_reachable_only_denominator_excludes_impossible_bars(self):
        hazard = Hazard()
        adverse = np.array([0.2, 1.1, -0.2, 0.9])
        possible = np.array([True, False, True, False])
        reversed_sign = np.array([True, False, False, False])
        hazard.settle_session(adverse, possible, reversed_sign)
        result = hazard.predict(np.array([0.4, 1.01]))["feasibility"]
        self.assertAlmostEqual(result[0], (1 + PRIOR/4.0) / (2 + PRIOR))
        self.assertEqual(result[1], 0.0)
        # If impossible bars leaked into the denominator this would differ.
        self.assertNotAlmostEqual(result[0], (1 + PRIOR/4.0) / (4 + PRIOR))

    def test_prediction_is_prior_session_only_and_does_not_update_memory(self):
        hazard = Hazard()
        ratios = np.array([0.25, 0.75])
        before = hazard.predict(ratios)
        for _ in range(3):
            repeated = hazard.predict(ratios)
            for name in before:
                np.testing.assert_array_equal(repeated[name], before[name])
        self.assertEqual((hazard.n, hazard.reversals, hazard.possible), (0, 0, 0))

        # Session outcomes are incorporated only after its predictions are frozen.
        frozen = {name: value.copy() for name, value in before.items()}
        hazard.settle_session(np.array([0.2, -0.1]), np.array([True, False]),
                              np.array([False, False]))
        for name in frozen:
            np.testing.assert_array_equal(frozen[name], before[name])
        after_prior_session = hazard.predict(ratios)
        self.assertEqual(hazard.n, 2)
        self.assertFalse(np.array_equal(after_prior_session["grid"], before["grid"]))

    def test_ratio_rejects_nan_and_negative_but_accepts_infinity(self):
        hazard = Hazard()
        for invalid in (-0.01, np.nan):
            with self.assertRaises(ValueError):
                hazard.predict(invalid)
        self.assertEqual(hazard.predict(np.inf)["grid"], 0.0)


if __name__ == "__main__":
    unittest.main()
