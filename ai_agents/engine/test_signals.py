"""Tests des signaux et de l'évaluation (données synthétiques, sans réseau)."""
import math
import random
import unittest
from unittest import mock

import signal_eval
import signals


def rows_from(closes):
    out = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        out.append({"t": i * 86400, "open": o, "high": max(o, c) * 1.01, "low": min(o, c) * 0.99,
                    "close": c, "volume": 100 + (i % 7)})
    return out


class SignalTests(unittest.TestCase):
    def setUp(self):
        rng = random.Random(3)
        c = [100.0]
        for _ in range(300):
            c.append(c[-1] * math.exp(rng.gauss(0, 0.03)))
        self.rows = rows_from(c)

    def test_all_signals_bounded(self):
        for name, f in signals.TECHNICAL.items():
            for t in range(signals.MIN_BARS, len(self.rows)):
                v = f(self.rows[: t + 1])
                self.assertTrue(-1 <= v <= 1, name)

    def test_uptrend_reads_bullish(self):
        up = rows_from([100 * 1.01 ** i for i in range(260)])
        for name in ("ema_trend", "momentum", "donchian", "rsi"):
            self.assertGreater(signals.TECHNICAL[name](up), 0, name)

    def test_zero_weights_give_zero_score(self):
        with mock.patch.object(signals, "load_weights", return_value={"weights": {}}):
            self.assertEqual(signals.compute("X", rows=self.rows)["score"], 0.0)

    def test_score_uses_learned_sign(self):
        with mock.patch.object(signals, "load_weights", return_value={"weights": {"rsi": -0.05}}):
            up = rows_from([100 * 1.01 ** i for i in range(260)])
            self.assertLess(signals.compute("X", rows=up)["score"], 0)   # contrarian appris

    def test_spearman(self):
        self.assertAlmostEqual(signal_eval.spearman(list(range(20)), list(range(20))), 1.0)
        self.assertAlmostEqual(signal_eval.spearman(list(range(20)), list(range(20))[::-1]), -1.0)

    def test_noise_gets_no_weight(self):
        rng = random.Random(5)
        pairs = [(rng.uniform(-1, 1), rng.gauss(0, 0.03)) for _ in range(2000)]
        self.assertEqual(signal_eval.stats(pairs, 3)["weight"], 0.0)

    def test_real_edge_gets_weight(self):
        rng = random.Random(6)
        pairs = []
        for _ in range(3000):
            x = rng.uniform(-1, 1)
            pairs.append((x, 0.02 * x + rng.gauss(0, 0.02)))
        self.assertGreater(signal_eval.stats(pairs, 1)["weight"], 0)


if __name__ == "__main__":
    unittest.main()
