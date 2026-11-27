import math
import unittest

from experiments.hold_work.matured import Memory


class MemoryTest(unittest.TestCase):
    def test_predictions_match_explicit_past_trade_kernel(self):
        memory = Memory()
        past = [(3., 2., 4., -3.), (2., 7., -1., 8.), (1., 0., 0., -1.)]
        query = (3., 4., 6.)
        self.assertEqual(set(memory.predict(*query).values()), {0.0})
        for event in past:
            memory.observe(*event)
        score = memory.predict(*query)
        a = math.tanh(query[1] / query[0] - 1)
        b = math.tanh((query[2] - query[1]) / query[0])
        for name in score:
            total, support = 0.0, 16.0
            for scale, price, volume, label in past:
                k = 1.0
                if name in ('price', 'interaction'):
                    k *= 1 + a * math.tanh(price / scale - 1)
                if name == 'interaction':
                    k *= 1 + b * math.tanh((volume - price) / scale)
                self.assertGreaterEqual(k, 0.0)
                total += k * label / scale
                support += k
            self.assertAlmostEqual(score[name], query[0] * total / support)
        self.assertEqual(memory.predict(*query), score)

    def test_invalid_matured_label_leaves_state_intact(self):
        memory = Memory()
        with self.assertRaises(ValueError):
            memory.observe(2., 1., 1., float('nan'))
        self.assertEqual(memory.mass, [0.] * 4)
        self.assertEqual(memory.value, [0.] * 4)
