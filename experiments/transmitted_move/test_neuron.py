import unittest

from experiments.transmitted_move.neuron import Transfer


class TransferEpisodeTests(unittest.TestCase):
    @staticmethod
    def opened_transfer():
        t = Transfer()
        self_none = t.step(0, 100.0, 100.0, 0.0)
        opened = t.step(1, 100.0, 102.0, 0.0)
        assert self_none is None and opened is None and t.live is not None
        return t

    def test_catch_up_and_leader_withdrawal_are_attributed_separately(self):
        catchup = self.opened_transfer()
        caught = catchup.step(2, 101.8, 102.0, 0.0)
        self.assertAlmostEqual(caught["catch"], 1.8)
        self.assertAlmostEqual(caught["withdraw"], 0.0)
        self.assertAlmostEqual(caught["closed"], caught["catch"] + caught["withdraw"])
        self.assertAlmostEqual(caught["q"], 1.0)
        self.assertEqual(caught["action"], 1)

        withdrawal = self.opened_transfer()
        withdrew = withdrawal.step(2, 100.0, 100.2, 0.0)
        self.assertAlmostEqual(withdrew["catch"], 0.0)
        self.assertAlmostEqual(withdrew["withdraw"], 1.8)
        self.assertAlmostEqual(withdrew["closed"], withdrew["catch"] + withdrew["withdraw"])
        self.assertAlmostEqual(withdrew["q"], -1.0)
        self.assertEqual(withdrew["action"], -1)

    def test_missing_common_second_cancels_anchor_and_live_episode(self):
        t = self.opened_transfer()
        self.assertIsNotNone(t.live)
        # Tick 2 is missing. A later apparent closure must not resolve old state.
        self.assertIsNone(t.step(3, 101.8, 102.0, 0.0))
        self.assertIsNone(t.live)
        # The gap bar can seed a fresh anchor, but old episode state is gone.
        self.assertEqual(t.anchor[0], 3)
        self.assertIsNone(t.step(4, 101.8, 104.0, 0.0))
        self.assertIsNotNone(t.live)
        self.assertEqual(t.live["anchor_time"], 3)

    def test_episode_expires_after_thirty_seconds(self):
        t = self.opened_transfer()  # opened at tick 1
        for tick in range(2, 32):
            self.assertIsNone(t.step(tick, 100.0, 102.0, 0.0))
            self.assertIsNotNone(t.live)
        # At age 31 the episode expires before it may resolve or linger.
        self.assertIsNone(t.step(32, 100.0, 102.0, 0.0))
        self.assertIsNone(t.live)
        self.assertIsNone(t.anchor)

    def test_contract_swap_preserves_attribution_and_action(self):
        original = self.opened_transfer()
        result = original.step(2, 101.8, 102.0, 0.0)

        swapped = Transfer()
        self.assertIsNone(swapped.step(0, 100.0, 100.0, -0.0))
        self.assertIsNone(swapped.step(1, 102.0, 100.0, -0.0))
        swapped_result = swapped.step(2, 102.0, 101.8, -0.0)
        self.assertEqual(swapped_result["leader"], 0)
        self.assertAlmostEqual(swapped_result["catch"], result["catch"])
        self.assertAlmostEqual(swapped_result["withdraw"], result["withdraw"])
        self.assertAlmostEqual(swapped_result["q"], result["q"])
        self.assertEqual(swapped_result["action"], result["action"])
        self.assertAlmostEqual(swapped_result["midpoint_change"], result["midpoint_change"])

    def test_price_sign_reflection_flips_direction_not_attribution(self):
        original = self.opened_transfer().step(2, 101.8, 102.0, 0.0)
        reflected = Transfer()
        self.assertIsNone(reflected.step(0, -100.0, -100.0, -0.0))
        self.assertIsNone(reflected.step(1, -100.0, -102.0, -0.0))
        mirrored = reflected.step(2, -101.8, -102.0, -0.0)
        self.assertAlmostEqual(mirrored["catch"], original["catch"])
        self.assertAlmostEqual(mirrored["withdraw"], original["withdraw"])
        self.assertAlmostEqual(mirrored["q"], original["q"])
        self.assertEqual(mirrored["action"], -original["action"])
        self.assertAlmostEqual(mirrored["midpoint_change"], -original["midpoint_change"])


if __name__ == "__main__":
    unittest.main()
