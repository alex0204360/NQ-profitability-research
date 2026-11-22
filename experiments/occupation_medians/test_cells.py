import random
import unittest
from replay import median_site, run
from symmetry import symmetric_median


class CellTests(unittest.TestCase):
    def test_mirror_and_mass_units(self):
        rng = random.Random(42)
        for _ in range(1000):
            rows = []
            for i in range(12):
                low = rng.randrange(40)
                rows.append(dict(low=low, high=low+rng.randrange(10)))
            weights = [rng.randrange(1,20) for _ in rows]
            center = symmetric_median(rows,weights)
            mirror = [dict(low=-r['high'],high=-r['low']) for r in rows]
            self.assertEqual(-center,symmetric_median(mirror,weights))
            self.assertEqual(center,symmetric_median(rows,[3*w for w in weights]))

    def test_tie_failure(self):
        rows = [dict(low=i,high=i) for i in range(12)]
        weights = [1]*11+[2]
        mirrored = [dict(low=-i,high=-i) for i in range(12)]
        self.assertEqual(median_site(rows,weights)-median_site(rows,[1]*12),1)
        self.assertEqual(median_site(mirrored,weights)-median_site(mirrored,[1]*12),0)

    def test_future_prices_do_not_move_signal(self):
        bars = {i:dict(open=i,low=i,high=i,close=i,volume=1+i) for i in range(19)}
        before = run({'example':bars})
        del bars[14]
        bars[17] = dict(open=100, high=110, low=40, close=80,volume=900)
        after = run({'example':bars})
        for left,right in zip(before,after,strict=True):
            for key in ['side','time_median','volume_median','unit']:
                self.assertEqual(left[key],right[key])
        self.assertNotEqual(before[0]['gross'],after[0]['gross'])


if __name__=='__main__':
    unittest.main()
