import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import market_scout as ms


class GreeksTest(unittest.TestCase):
    # Hull, Options Futures and Other Derivatives: S=49, K=50, T=20 weeks, r=5%, vol=20%
    def test_call_matches_hull(self):
        g = ms.bsm_greeks(49, [50], 0.3846, [0.2], call=True, rate=0.05)
        self.assertAlmostEqual(g["delta"][0], 0.522, places=3)
        self.assertAlmostEqual(g["gamma"][0], 0.066, places=3)
        self.assertAlmostEqual(g["vega"][0], 0.121, places=3)
        self.assertAlmostEqual(g["theta"][0] * 365, -4.31, places=2)

    def test_put_call_delta_parity(self):
        c = ms.bsm_greeks(49, [50], 0.3846, [0.2], call=True, rate=0.05)
        p = ms.bsm_greeks(49, [50], 0.3846, [0.2], call=False, rate=0.05)
        self.assertAlmostEqual(c["delta"][0] - p["delta"][0], 1.0, places=6)


class PositionSizeTest(unittest.TestCase):
    def test_options_contracts(self):
        r = ms.position_size(25000, 1, 4.20, 2.10, 100)
        self.assertEqual(r["units"], 1)
        self.assertEqual(r["risk_dollars"], 250.0)

    def test_risk_too_small_for_one_unit(self):
        self.assertEqual(ms.position_size(10000, 1, 2.50, 1.25, 100)["units"], 0)


if __name__ == "__main__":
    unittest.main()
