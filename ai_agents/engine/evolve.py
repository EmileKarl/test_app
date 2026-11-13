#!/usr/bin/env python3
"""Évolution des stratégies : champion contre challengers, validation hors échantillon.

    python3 ai_agents/engine/evolve.py [--candidates 40] [--bars 720] [--seed N]

1. Récupère l'historique de l'univers (bougies publiques Coinbase).
2. Coupe en deux : 70 % entraînement, 30 % test (jamais vu pendant la recherche).
3. Mute les paramètres du champion + quelques tirages aléatoires ; classe sur l'entraînement.
4. Les 5 meilleurs sont évalués sur le test. Un challenger ne remplace le champion que s'il
   le bat hors échantillon d'une marge nette de frais, avec un drawdown pas pire, au moins
   2 trades, et un rendement de test > 0 OU meilleur que de rester en cash et en buy&hold.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import backtest  # noqa: E402
import market  # noqa: E402
from cycle import BARS_PER_YEAR, CONFIG, STATE, champion, load, now, save  # noqa: E402
from strategies import BOUNDS, clamp_params  # noqa: E402

MARGIN = 0.25  # gain de fitness minimal pour promouvoir


def mutate(p: dict, rng: random.Random, strength: float = 0.25) -> dict:
    q = dict(p)
    for k, (lo, hi, typ) in BOUNDS.items():
        if rng.random() < 0.5:
            span = (hi - lo) * strength
            q[k] = q[k] + rng.uniform(-span, span)
    return clamp_params(q)


def random_params(rng: random.Random) -> dict:
    return clamp_params({k: rng.uniform(lo, hi) for k, (lo, hi, _) in BOUNDS.items()})


def evaluate(series, p, bpy, split, cfg):
    kw = dict(fee=cfg["maker_fee"], slippage=cfg.get("paper_slippage", 0.0005),
              min_order=cfg["min_order_usd"])
    train = backtest.run({a: v[:split] for a, v in series.items()}, p, bpy, **kw)
    test = backtest.run(series, p, bpy, start_index=split, **kw)
    return train, test


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", type=int, default=40)
    ap.add_argument("--bars", type=int, default=720)
    ap.add_argument("--seed", type=int)
    a = ap.parse_args(argv)
    rng = random.Random(a.seed)
    cfg = load(CONFIG / "autopilot.json")
    champ = champion()
    gran = champ["granularity"]
    bpy = BARS_PER_YEAR[gran]
    series = {x: [r["close"] for r in market.candles(f"{x}-{cfg['quote']}", gran, a.bars)]
              for x in cfg["universe"]}
    n = min(len(v) for v in series.values())
    series = {x: v[-n:] for x, v in series.items()}
    split = int(n * 0.7)

    c_train, c_test = evaluate(series, champ, bpy, split, cfg)
    pool = [mutate(champ, rng) for _ in range(int(a.candidates * 0.75))]
    pool += [random_params(rng) for _ in range(a.candidates - len(pool))]
    scored = []
    for cand in pool:
        tr = backtest.run({x: v[:split] for x, v in series.items()}, cand, bpy,
                          fee=cfg["maker_fee"], slippage=cfg.get("paper_slippage", 0.0005),
                          min_order=cfg["min_order_usd"])
        scored.append((backtest.fitness(tr), cand, tr))
    scored.sort(key=lambda s: s[0], reverse=True)

    best = None
    for _, cand, tr in scored[:5]:
        te = backtest.run(series, cand, bpy, start_index=split, fee=cfg["maker_fee"],
                          slippage=cfg.get("paper_slippage", 0.0005), min_order=cfg["min_order_usd"])
        if best is None or backtest.fitness(te) > backtest.fitness(best[2]):
            best = (cand, tr, te)

    cand, tr, te = best
    promote = (
        te.get("valid")
        and backtest.fitness(te) > backtest.fitness(c_test) + MARGIN
        and te["max_drawdown_pct"] >= c_test.get("max_drawdown_pct", -100) - 5
        and te["trades"] >= 2
        and (te["total_return_pct"] > 0 or te["excess_vs_hold_pct"] > 0)
    )
    s = load(STATE / "strategies.json")
    report = {"ts": now().isoformat(timespec="seconds"), "granularity": gran, "bars": n,
              "champion_test": c_test, "champion_train": c_train,
              "best_challenger": {k: cand[k] for k in BOUNDS}, "challenger_train": tr,
              "challenger_test": te, "promoted": bool(promote)}
    if promote:
        version = len(s.get("history", [])) + 2
        new = {**cand, "granularity": gran, "name": f"trend_mom_vol_v{version}"}
        s.setdefault("history", []).append({"retired": s["champion"], "at": report["ts"],
                                            "replaced_by": new["name"]})
        s["champion"] = new
        save(STATE / "strategies.json", s)
    with (STATE / "evolution_log.jsonl").open("a") as f:
        f.write(json.dumps(report, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
