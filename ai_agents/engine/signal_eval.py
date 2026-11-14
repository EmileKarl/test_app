#!/usr/bin/env python3
"""Mesure honnête du pouvoir prédictif de chaque signal, puis mise à jour des poids.

    python3 ai_agents/engine/signal_eval.py [--horizon 3] [--bars 720]

Pour chaque signal et chaque actif : valeur du signal au jour t (calculée uniquement avec
le passé) contre le rendement des `horizon` jours suivants. On mesure :
  - IC : corrélation de rang (Spearman) signal / rendement futur, tous actifs confondus ;
  - t-stat ≈ IC × √(n_effectif), avec n_effectif = n / horizon (rendements qui se chevauchent) ;
  - taux de réussite (signe du signal = signe du rendement).
Poids = IC si |t| ≥ 3 (correction des tests multiples) ET même signe sur les deux moitiés de l'historique (stabilité), sinon 0.
Le poids peut être négatif : le signal est alors utilisé à contre-sens (contrarian), c'est la
donnée qui décide, pas une croyance.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import market  # noqa: E402
import signals  # noqa: E402

# |t| ≥ 3 : correction des tests multiples (≈ 12 signaux × plusieurs horizons testés).
T_MIN = 3.0
ASSETS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "AVAX", "NEAR", "SUI"]


def rank(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    for pos, i in enumerate(order):
        r[i] = pos
    return r


def spearman(x, y):
    if len(x) < 10:
        return 0.0
    rx, ry = rank(x), rank(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    vy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return cov / (vx * vy) if vx and vy else 0.0


def stats(pairs, horizon):
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    ic = spearman(xs, ys)
    n_eff = max(1, len(pairs) / horizon)
    half = len(pairs) // 2
    ic1 = spearman(xs[:half], ys[:half])
    ic2 = spearman(xs[half:], ys[half:])
    nz = [(x, y) for x, y in pairs if x != 0]
    hit = sum(1 for x, y in nz if (x > 0) == (y > 0)) / len(nz) if nz else None
    t = ic * math.sqrt(n_eff)
    stable = (ic1 > 0) == (ic2 > 0) and abs(ic1) > 0.01 and abs(ic2) > 0.01
    return {"ic": round(ic, 4), "t": round(t, 2), "n": len(pairs), "hit_rate": round(hit, 3) if hit else None,
            "ic_first_half": round(ic1, 4), "ic_second_half": round(ic2, 4), "stable": stable,
            "weight": round(ic, 4) if abs(t) >= T_MIN and stable else 0.0}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=3, help="jours de rendement futur")
    ap.add_argument("--bars", type=int, default=720)
    a = ap.parse_args(argv)
    h = a.horizon
    pairs = {k: [] for k in signals.TECHNICAL}
    btc_rows = None
    for asset in ASSETS:
        try:
            rows = market.candles(f"{asset}-USDC", "ONE_DAY", bars=a.bars)
        except Exception:
            continue
        if asset == "BTC":
            btc_rows = rows
        for t in range(signals.MIN_BARS, len(rows) - h):
            window = rows[: t + 1]
            fwd = rows[t + h]["close"] / rows[t]["close"] - 1
            for name, f in signals.TECHNICAL.items():
                pairs[name].append((f(window), fwd))

    results = {name: stats(p, h) for name, p in pairs.items()}

    # Fear & Greed contre le rendement futur de BTC.
    try:
        fng = dict((dt.date.fromtimestamp(ts).isoformat(), v) for ts, v in signals.fear_greed_history(1000))
        fp = []
        for i in range(len(btc_rows) - h):
            day = dt.datetime.fromtimestamp(btc_rows[i]["t"], dt.timezone.utc).date().isoformat()
            if day in fng:
                fp.append((signals.s_fear_greed(fng[day]), btc_rows[i + h]["close"] / btc_rows[i]["close"] - 1))
        results["fear_greed"] = stats(fp, h)
    except Exception as e:
        results["fear_greed"] = {"error": str(e), "weight": 0.0}

    # Financement OKX (historique court, ~3 mois) contre le rendement futur de BTC.
    try:
        fh = signals.okx_funding_history("BTC", 100)
        by_day = {}
        for ts, r in fh:
            by_day.setdefault(dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat(), []).append(r)
        fp = []
        for i in range(len(btc_rows) - h):
            day = dt.datetime.fromtimestamp(btc_rows[i]["t"], dt.timezone.utc).date().isoformat()
            if day in by_day:
                rate = sum(by_day[day]) / len(by_day[day])
                fp.append((signals.s_funding(rate), btc_rows[i + h]["close"] / btc_rows[i]["close"] - 1))
        results["funding"] = stats(fp, h)
    except Exception as e:
        results["funding"] = {"error": str(e), "weight": 0.0}

    out = {"evaluated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "horizon_days": h, "assets": ASSETS, "results": results,
           "weights": {k: v.get("weight", 0.0) for k, v in results.items()}}
    signals.WEIGHTS.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
