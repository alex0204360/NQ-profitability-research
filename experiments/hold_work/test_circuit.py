import unittest

from experiments.hold_work.circuit import Head


class CircuitInvarianceTests(unittest.TestCase):
    def run_path(self, direction, entry, scale, closes, volumes=None, prior=10):
        volumes = volumes or [prior] * len(closes)
        head = Head(direction, entry, scale)
        out = []
        for close, volume in zip(closes, volumes):
            out.append(head.step(entry, max(entry, close), min(entry, close), close,
                                 volume, prior))
        return out

    def test_causal_prefix_is_independent_of_future(self):
        prefix = [100.5, 101.0, 100.75]
        a = self.run_path(1, 100, 1, prefix + [103, 96])
        b = self.run_path(1, 100, 1, prefix + [80, 140])
        self.assertEqual(a[:len(prefix)], b[:len(prefix)])

    def test_sign_reflection_preserves_position_relative_outputs(self):
        # Reflect price coordinates about entry and invert the position direction.
        entry, scale = 125.0, 1.5
        closes = [125.5, 127.0, 126.0, 127.5, 126.5]
        original = self.run_path(1, entry, scale, closes, [8, 12, 10, 16, 7], 10)
        reflected_closes = [2 * entry - x for x in closes]
        reflected = self.run_path(-1, entry, scale, reflected_closes,
                                  [8, 12, 10, 16, 7], 10)
        for lhs, rhs in zip(original, reflected):
            self.assertEqual(lhs, rhs)

    def test_equal_mass_cells_stay_equal_at_normal_mass(self):
        out = self.run_path(1, 50, 2, [51, 52, 51, 53, 50], [10] * 5, prior=10)
        for row in out:
            self.assertAlmostEqual(row['participation'], 1.0)
            self.assertAlmostEqual(row['price'], row['volume'])

    def test_repeated_erased_repair_is_bounded(self):
        # Rebuild a repair credit then erase it with a retreat; repeat the cycle.
        head = Head(1, 0, 1)
        sequence = [1, 2, 1, 1.5, 1, 1.5, 1]
        rows = [head.step(0, x, x, x, 10, 10) for x in sequence]
        self.assertEqual([r['erased'] for r in rows], [0, 0, 0, 0, 0.5, 0, 0.5])
        self.assertEqual([r['repair'] for r in rows], [0, 0, 0, 0.5, 0, 0.5, 0])
        self.assertTrue(all(0 <= r['repair'] <= 0.5 for r in rows))

    def test_trail_waits_for_scale_eligibility(self):
        head = Head(1, 100, 2)
        before = head.step(100, 100.5, 100, 100.5, 10, 10)
        self.assertFalse(before['eligible'])
        self.assertEqual(before['trail'], 2)
        eligible = head.step(100, 102, 100.5, 102, 10, 10)
        self.assertTrue(eligible['eligible'])
        self.assertEqual(eligible['trail'], 4)
        after_peak = head.step(100, 102, 100, 101, 10, 10)
        self.assertTrue(after_peak['eligible'])
        self.assertEqual(after_peak['trail'], 3)


if __name__ == '__main__':
    unittest.main()
