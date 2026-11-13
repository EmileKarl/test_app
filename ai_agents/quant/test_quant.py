import math
import unittest

import quant


class QuantTests(unittest.TestCase):
    def test_max_drawdown(self):
        self.assertAlmostEqual(quant.max_drawdown([100, 120, 60, 90]), -0.5)

    def test_stats_constant_growth(self):
        prices = [100 * 1.01 ** i for i in range(50)]
        prices[10] *= 1.001  # évite une volatilité nulle
        s = quant.stats(prices)
        self.assertAlmostEqual(s["total_return_pct"], (1.01 ** 49 - 1) * 100, places=6)
        self.assertGreater(s["sharpe"], 0)

    def test_kelly(self):
        k = quant.kelly(0.5, 2.0)
        self.assertAlmostEqual(k["full_kelly_pct"], 25.0)
        self.assertEqual(quant.kelly(0.4, 1.0)["fractional_kelly_0.25_pct"], 0.0)

    def test_position_size_risk_respected(self):
        out = quant.position_size(1000, 1, 100, 95, fee_pct=0)
        self.assertAlmostEqual(out["quantity"] * 5, 10.0)

    def test_var_positive_loss(self):
        prices = [100 * math.exp(0.02 * ((-1) ** i) * (1 + i % 3)) for i in range(200)]
        v = quant.value_at_risk(prices, 0.95)
        self.assertGreater(v["historical_cvar_loss_pct"], 0)
        self.assertGreaterEqual(v["historical_cvar_loss_pct"], v["historical_var_loss_pct"])

    def test_montecarlo_probabilities_sum(self):
        prices = [100 + (i % 7) - 3 + i * 0.1 for i in range(100)]
        mc = quant.monte_carlo(prices, days=20, n_paths=500, target=115, stop=90, zero_drift=True)
        total = mc["prob_hit_target_first"] + mc["prob_hit_stop_first"] + mc["prob_neither"]
        self.assertAlmostEqual(total, 1.0)

    def test_rejects_bad_prices(self):
        with self.assertRaises(ValueError):
            quant._clean_prices([1, 0, 2])


if __name__ == "__main__":
    unittest.main()
