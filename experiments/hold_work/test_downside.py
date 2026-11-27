import unittest

from experiments.hold_work.downside import TailMemory, scales


class DownsideScaleAndMemoryTests(unittest.TestCase):
    def make_scales(self):
        return scales(entry_range=1.0, forecast=1.0, roughness=1.0, minutes_left=1)

    def test_twenty_observation_warmup(self):
        memory = TailMemory()
        scale = self.make_scales()
        for loss in range(1, 20):
            self.assertIsNone(memory.predict(scale))
            memory.observe(scale, loss)
            self.assertEqual(memory.count, loss)
        self.assertIsNone(memory.predict(scale))
        memory.observe(scale, 20)
        self.assertEqual(memory.count, 20)
        self.assertEqual(memory.predict(scale), {name: 16.0 for name in scale})

    def test_exact_empirical_ranks_without_interpolation(self):
        memory = TailMemory()
        scale = self.make_scales()
        for loss in range(1, 22):
            memory.observe(scale, loss)
            if loss == 20:
                self.assertEqual(memory.predict(scale), {name: 16.0 for name in scale})
        # ceil(.8 * 21) = 17: exact 17th order statistic, not interpolation.
        self.assertEqual(memory.predict(scale), {name: 17.0 for name in scale})

    def test_unit_transform_scales_all_point_forecasts(self):
        original_scale = scales(3.0, -6.0, 2.0, 16)
        factor = 4.0
        transformed_scale = scales(3.0 * factor, -6.0 * factor,
                                   2.0 * factor, 16)
        self.assertEqual(original_scale,
                         {"constant": 1.0, "range": 3.0, "clock": 12.0, "distance": 9.0})
        self.assertEqual(transformed_scale,
                         {"constant": 1.0, "range": 12.0, "clock": 48.0, "distance": 36.0})

        original, transformed = TailMemory(), TailMemory()
        for loss in range(1, 21):
            original.observe(original_scale, float(loss))
            transformed.observe(transformed_scale, factor * float(loss))
        original_prediction = original.predict(original_scale)
        transformed_prediction = transformed.predict(transformed_scale)
        for name in original_prediction:
            self.assertAlmostEqual(transformed_prediction[name],
                                   factor * original_prediction[name])

    def test_forecast_sign_reflection_preserves_all_scales(self):
        long_scale = scales(2.5, 7.25, 1.5, 9)
        short_scale = scales(2.5, -7.25, 1.5, 9)
        self.assertEqual(long_scale, short_scale)

    def test_duration_is_capped_by_time_to_cutoff(self):
        # Huge forecast movement cannot imply more diffusion time than remains.
        candidate = scales(entry_range=2.0, forecast=100.0, roughness=0.25,
                           minutes_left=9)
        self.assertEqual(candidate["clock"], 6.0)
        self.assertEqual(candidate["distance"], candidate["clock"])

        # At or past cutoff the registered minimum is one available minute.
        for minutes_left in (0, -5):
            capped = scales(entry_range=2.0, forecast=100.0, roughness=0.25,
                            minutes_left=minutes_left)
            self.assertEqual(capped["clock"], 2.0)
            self.assertEqual(capped["distance"], 2.0)

    def test_unavailable_roughness_uses_one_step_fallback(self):
        fallback = scales(entry_range=3.5, forecast=40.0, roughness=None,
                          minutes_left=100)
        self.assertEqual(fallback["distance"], 3.5)
        self.assertEqual(fallback["clock"], 35.0)
        self.assertEqual(fallback["range"], 3.5)


if __name__ == "__main__":
    unittest.main()
