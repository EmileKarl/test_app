"""Tests du planificateur de grille (marché simulé, aucune requête réseau)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import grid

CFG = {"quote": "USDC", "grid": {
    "assets": ["BTC", "DOGE", "ETH"], "order_usd": 3.0, "min_order_usd": 1.2,
    "max_sell_fraction": 0.25, "vol_multiplier": 1.0, "min_spacing": 0.025,
    "max_spacing": 0.07, "take_profit_multiple": 1.0, "cash_reserve_fraction": 0.05}}
LIMITS = {"allowed_products": ["BTC-USDC", "DOGE-USDC", "ETH-USDC"], "max_order_usd": 10,
          "max_daily_volume_usd": 80, "max_daily_loss_usd": 8, "max_drawdown_pct": 20,
          "max_asset_pct_of_portfolio": 100, "auto_max_order_usd": 5, "allow_derivatives": False}
PRODUCTS = {
    "BTC-USDC": {"price": "68000", "base_increment": "0.00000001", "price_increment": "0.01", "quote_min_size": "1"},
    "DOGE-USDC": {"price": "0.065", "base_increment": "0.1", "price_increment": "0.00001", "quote_min_size": "1"},
    "ETH-USDC": {"price": "1900", "base_increment": "0.00000001", "price_increment": "0.01", "quote_min_size": "1"},
}


class GridPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "state").mkdir()
        (root / "paper").mkdir()
        self.root = root
        self.limits = dict(LIMITS)
        patches = [
            mock.patch.object(grid, "ROOT", root),
            mock.patch.object(grid, "load", side_effect=lambda p: CFG if "autopilot" in str(p) else self.limits),
            mock.patch.object(grid.market, "product", side_effect=lambda pid: PRODUCTS[pid]),
            mock.patch.object(grid, "daily_vol", return_value=0.02),
            mock.patch.object(grid, "live_volume_today", return_value=0.0),
            mock.patch.object(grid, "asset_score", return_value=0.0),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, balances, open_orders=()):
        return grid.plan({"balances": balances, "open_orders": list(open_orders)})

    def test_kill_gives_empty_plan(self):
        (self.root / "state" / "KILL").write_text("test")
        out = self.plan({"BTC": 0.001, "USDC": 50})
        self.assertEqual(out["place"], [])
        self.assertEqual(out["cancel"], [])

    def test_one_sell_one_buy_per_asset_and_sides_correct(self):
        out = self.plan({"BTC": 0.001, "DOGE": 100, "ETH": 0.01, "USDC": 30})
        for pid in PRODUCTS:
            sides = [o["side"] for o in out["place"] if o["product_id"] == pid]
            self.assertLessEqual(sides.count("SELL"), 1)
            self.assertLessEqual(sides.count("BUY"), 1)
        for o in out["place"]:
            px = float(PRODUCTS[o["product_id"]]["price"])
            self.assertTrue(o["post_only"])
            self.assertEqual(o["time_in_force"], "GTC")
            if o["side"] == "SELL":
                self.assertGreater(float(o["limit_price"]), px)
            else:
                self.assertLess(float(o["limit_price"]), px)
                self.assertGreater(float(o["attached_take_profit_price"]),
                                   float(o["limit_price"]) * (1 + 2 * 0.0025))

    def test_idempotent_when_orders_in_band(self):
        orders = [{"order_id": "1", "product_id": "BTC-USDC", "side": "SELL", "limit_price": "69700", "base_size": "0.00004"}]
        out = self.plan({"BTC": 0.001, "USDC": 0}, orders)
        self.assertFalse([o for o in out["place"] if o["product_id"] == "BTC-USDC"])
        self.assertEqual(out["cancel"], [])

    def test_recentre_boundary(self):
        s = 0.025  # vol 2 % -> écart min 2,5 %
        near = {"order_id": "a", "product_id": "BTC-USDC", "side": "SELL",
                "limit_price": str(68000 * (1 + 2.49 * s)), "base_size": "0.00004"}
        far = dict(near, order_id="b", limit_price=str(68000 * (1 + 2.51 * s)))
        self.assertEqual(self.plan({"BTC": 0.001, "USDC": 0}, [near])["cancel"], [])
        self.assertEqual(len(self.plan({"BTC": 0.001, "USDC": 0}, [far])["cancel"]), 1)

    def test_resize_after_cancel_uses_total_position(self):
        # Cas réel de l'audit : vente DOGE trop loin, 17,8 bloqués + 34,7 disponibles.
        far = {"order_id": "d", "product_id": "DOGE-USDC", "side": "SELL", "limit_price": "0.0700", "base_size": "17.8"}
        out = self.plan({"DOGE": 34.7, "USDC": 0}, [far])
        self.assertEqual(len(out["cancel"]), 1)
        sell = [o for o in out["place"] if o["product_id"] == "DOGE-USDC"][0]
        total_value = (34.7 + 17.8) * 0.065
        self.assertLessEqual(sell["notional_usd"] / (1.025), max(1.2, total_value * 0.25) + 0.01)
        self.assertLess(float(sell["base_size"]), 30)  # jamais ~64 % de la position

    def test_buy_budget_fair_and_capped(self):
        out = self.plan({"USDC": 6.0})
        buys = [o for o in out["place"] if o["side"] == "BUY"]
        self.assertEqual(len(buys), 3)  # 6 × 0,95 / 3 = 1,9 $ chacun, au-dessus du minimum
        self.assertLessEqual(sum(o["notional_usd"] for o in buys), 6.0 * 0.95 + 0.01)
        amounts = [o["notional_usd"] for o in buys]
        self.assertLess(max(amounts) - min(amounts), 0.05)

    def test_unauthorised_product_skipped(self):
        self.limits = dict(LIMITS, allowed_products=["BTC-USDC"])
        out = self.plan({"DOGE": 100, "USDC": 0})
        self.assertFalse([o for o in out["place"] if o["product_id"] == "DOGE-USDC"])
        self.assertTrue(any(s["asset"] == "DOGE" for s in out["skipped"]))

    def test_daily_volume_limit_blocks(self):
        with mock.patch.object(grid, "live_volume_today", return_value=79.0):
            out = self.plan({"BTC": 0.001, "USDC": 0})
        self.assertEqual(out["place"], [])

    def test_approval_flag_above_auto_threshold(self):
        CFG["grid"]["order_usd"] = 8.0
        try:
            out = self.plan({"BTC": 0.01, "USDC": 0})
        finally:
            CFG["grid"]["order_usd"] = 3.0
        self.assertTrue(all(o["needs_user_approval"] for o in out["place"]))

    def test_sell_ladder_uses_whole_position_within_limits(self):
        CFG["grid"]["ladder"] = {"ETH": 4}
        try:
            existing = [{"order_id": "e1", "product_id": "ETH-USDC", "side": "SELL",
                         "limit_price": str(1900 * 1.025), "base_size": "0.0015"}]
            out = self.plan({"ETH": 0.006, "USDC": 0}, existing)
        finally:
            CFG["grid"].pop("ladder")
        rungs = [o for o in out["place"] if o["product_id"] == "ETH-USDC"]
        self.assertEqual(len(rungs), 3)                       # 4 paliers - 1 existant
        self.assertEqual(out["cancel"], [])                   # le palier 1 est conservé
        prices = sorted(float(o["limit_price"]) for o in rungs)
        self.assertGreater(prices[0], 1900 * 1.04)            # paliers 2, 3, 4 au-dessus du 1er
        self.assertLessEqual(sum(float(o["base_size"]) for o in rungs), 0.006)
        self.assertTrue(all(o["notional_usd"] <= 5 for o in rungs))

    def test_bearish_score_widens_buys_and_strong_bearish_pauses(self):
        base = [o for o in self.plan({"USDC": 6.0})["place"] if o["product_id"] == "BTC-USDC"][0]
        with mock.patch.object(grid, "asset_score", return_value=-0.5):
            wide = [o for o in self.plan({"USDC": 6.0})["place"] if o["product_id"] == "BTC-USDC"][0]
        self.assertLess(float(wide["limit_price"]), float(base["limit_price"]))
        with mock.patch.object(grid, "asset_score", return_value=-0.8):
            out = self.plan({"USDC": 6.0})
        self.assertFalse([o for o in out["place"] if o["side"] == "BUY"])

    def test_bullish_score_raises_sells(self):
        base = [o for o in self.plan({"BTC": 0.001})["place"] if o["side"] == "SELL"][0]
        with mock.patch.object(grid, "asset_score", return_value=0.5):
            high = [o for o in self.plan({"BTC": 0.001})["place"] if o["side"] == "SELL"][0]
        self.assertGreater(float(high["limit_price"]), float(base["limit_price"]))

    def test_buy_first_mode_never_sells_holdings(self):
        CFG["grid"]["sell_existing_holdings"] = False
        try:
            out = self.plan({"BTC": 0.01, "DOGE": 500, "USDC": 9.0})
        finally:
            CFG["grid"].pop("sell_existing_holdings")
        self.assertFalse([o for o in out["place"] if o["side"] == "SELL"])
        buys = [o for o in out["place"] if o["side"] == "BUY"]
        self.assertTrue(buys)
        for o in buys:  # la revente attachée couvre les frais aller-retour
            self.assertGreaterEqual(float(o["attached_take_profit_price"]) / float(o["limit_price"]), 1.024)

    def test_buy_ladder_levels_and_take_profit(self):
        CFG["grid"].update({"sell_existing_holdings": False, "buy_levels": [0.015, 0.03, 0.045], "take_profit_pct": 0.02, "order_usd": 2.0})
        try:
            out = self.plan({"BTC": 0.01, "USDC": 30.0})
            # une revente attachée existante (SELL) ne doit jamais être annulée
            tp = [{"order_id": "tp", "product_id": "BTC-USDC", "side": "SELL", "limit_price": "90000", "base_size": "0.00003"}]
            out2 = self.plan({"USDC": 30.0}, tp)
        finally:
            for k in ("sell_existing_holdings", "buy_levels", "take_profit_pct"):
                CFG["grid"].pop(k)
            CFG["grid"]["order_usd"] = 3.0
        btc = sorted(float(o["limit_price"]) for o in out["place"] if o["product_id"] == "BTC-USDC")
        self.assertEqual(len(btc), 3)
        for got, lvl in zip(sorted(btc, reverse=True), [0.015, 0.03, 0.045]):
            self.assertAlmostEqual(got, 68000 * (1 - lvl), delta=1)
        for o in out["place"]:
            self.assertAlmostEqual(float(o["attached_take_profit_price"]) / float(o["limit_price"]), 1.02, places=3)
            self.assertLessEqual(o["notional_usd"], 2.0)
        self.assertEqual(out2["cancel"], [])


if __name__ == "__main__":
    unittest.main()
