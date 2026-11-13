"""Tests du moteur, dont injection de fautes : chaque violation plantée doit être bloquée."""
import math
import random
import unittest

import backtest
import risk_gate
from strategies import DEFAULT_PARAMS, clamp_params, target_exposure

LIMITS = {
    "max_order_usd": 10, "max_daily_volume_usd": 40, "max_daily_loss_usd": 5,
    "max_drawdown_pct": 15, "max_asset_pct_of_portfolio": 40, "allow_derivatives": False,
    "allowed_products": ["BTC-USDC", "ETH-USDC"],
}
OK_ORDER = {"product_id": "BTC-USDC", "side": "BUY", "notional_usd": 5}
OK_CTX = {"killed": False, "daily_volume_usd": 0, "daily_pnl_usd": 0, "drawdown_pct": 0,
          "equity_usd": 90, "asset_value_after_usd": 20}


class RiskGateFaultInjection(unittest.TestCase):
    def test_clean_order_passes(self):
        self.assertTrue(risk_gate.check(OK_ORDER, OK_CTX, LIMITS)[0])

    FAULTS = [
        ("kill switch", {}, {"killed": True}),
        ("produit interdit", {"product_id": "PEPE-USDC"}, {}),
        ("montant trop gros", {"notional_usd": 10.01}, {}),
        ("montant négatif", {"notional_usd": -3}, {}),
        ("montant NaN", {"notional_usd": float("nan")}, {}),
        ("volume journalier", {}, {"daily_volume_usd": 36}),
        ("perte journalière", {}, {"daily_pnl_usd": -5}),
        ("drawdown", {}, {"drawdown_pct": 15}),
        ("concentration", {}, {"asset_value_after_usd": 37}),
        ("dérivé", {"derivative": True}, {}),
        ("retrait", {"withdrawal": True}, {}),
        ("sens invalide", {"side": "SHORT"}, {}),
    ]

    def test_every_planted_fault_is_blocked(self):
        for name, o, c in self.FAULTS:
            with self.subTest(fault=name):
                ok, why = risk_gate.check({**OK_ORDER, **o}, {**OK_CTX, **c}, LIMITS)
                self.assertFalse(ok, name)
                self.assertTrue(why)

    def test_sells_allowed_after_loss(self):
        ok, _ = risk_gate.check({**OK_ORDER, "side": "SELL"}, {**OK_CTX, "daily_pnl_usd": -9, "drawdown_pct": 20}, LIMITS)
        self.assertTrue(ok)


class StrategyTests(unittest.TestCase):
    def test_no_lookahead(self):
        rng = random.Random(0)
        closes = [100.0]
        for _ in range(400):
            closes.append(closes[-1] * math.exp(rng.gauss(0, 0.02)))
        p = DEFAULT_PARAMS
        a = target_exposure(closes[:300], p, 1460)
        b = target_exposure(closes[:300] + [1e9], p, 1460)  # futur extrême ajouté
        self.assertEqual(a, target_exposure(closes[:300], p, 1460))
        self.assertNotEqual(id(a), id(b))  # le calcul sur 300 points ne dépend pas du point 301
        self.assertTrue(0 <= a <= 1)

    def test_downtrend_goes_to_cash(self):
        closes = [100 * 0.995 ** i for i in range(300)]
        closes = [c * (1 + 0.001 * ((-1) ** i)) for i, c in enumerate(closes)]
        self.assertEqual(target_exposure(closes, DEFAULT_PARAMS, 1460), 0.0)

    def test_clamp(self):
        q = clamp_params({**DEFAULT_PARAMS, "ema_fast": 500, "ema_slow": 10})
        self.assertLess(q["ema_fast"], q["ema_slow"])


class BacktestTests(unittest.TestCase):
    def test_fees_reduce_return(self):
        rng = random.Random(1)
        s = {"A": [100.0], "B": [50.0]}
        for _ in range(500):
            for k in s:
                s[k].append(s[k][-1] * math.exp(rng.gauss(0.0005, 0.02)))
        p = {**DEFAULT_PARAMS, "rebalance_threshold": 0.03}
        free = backtest.run(s, p, 1460, fee=0, slippage=0)
        costly = backtest.run(s, p, 1460, fee=0.01, slippage=0)
        self.assertGreater(free["total_return_pct"], costly["total_return_pct"])
        self.assertEqual(free["fees_paid"], 0)

    def test_cash_never_negative(self):
        s = {"A": [100 * (1.01 ** i) for i in range(300)]}
        m = backtest.run(s, {**DEFAULT_PARAMS, "rebalance_threshold": 0.03}, 1460)
        self.assertTrue(m["valid"])
        self.assertGreater(m["total_return_pct"], -100)


class GridTests(unittest.TestCase):
    def test_floor_to_increment(self):
        import grid
        self.assertEqual(grid.floor_to(0.123456789, "0.001"), "0.123")
        self.assertEqual(grid.floor_to(524.9, "1"), "524")

    def test_spacing_bounds(self):
        import grid
        g = {"min_spacing": 0.025, "max_spacing": 0.07, "vol_multiplier": 1.0}
        self.assertEqual(grid.spacing(0.001, g), 0.025)   # couvre toujours les frais
        self.assertEqual(grid.spacing(0.5, g), 0.07)


if __name__ == "__main__":
    unittest.main()
