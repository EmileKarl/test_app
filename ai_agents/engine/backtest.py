"""Backtest multi-actifs avec frais, seuil de rééquilibrage et ordre minimum.

Le portefeuille répartit son capital à parts égales entre les actifs de l'univers ;
chaque part est investie selon l'exposition cible de la stratégie, le reste en USDC.
"""

from __future__ import annotations

import math

from strategies import min_history, target_exposure


def run(series: dict[str, list[float]], p: dict, bars_per_year: float,
        fee: float = 0.0025, slippage: float = 0.0005, min_order: float = 1.0,
        start_cash: float = 100.0, start_index: int | None = None) -> dict:
    assets = list(series)
    n = min(len(v) for v in series.values())
    series = {a: v[-n:] for a, v in series.items()}
    start = max(min_history(p), start_index or 0)
    cash, qty = start_cash, {a: 0.0 for a in assets}
    equity_curve, fees_paid, trades = [], 0.0, 0
    cost = fee + slippage
    for i in range(start, n):
        prices = {a: series[a][i] for a in assets}
        equity = cash + sum(qty[a] * prices[a] for a in assets)
        for a in assets:
            tgt_w = target_exposure(series[a][: i + 1], p, bars_per_year) / len(assets)
            cur_w = qty[a] * prices[a] / equity if equity else 0
            if abs(tgt_w - cur_w) < p["rebalance_threshold"] / len(assets):
                continue
            delta_value = (tgt_w - cur_w) * equity
            if abs(delta_value) < min_order:
                continue
            if delta_value > 0:
                delta_value = min(delta_value, cash / (1 + cost))
                if delta_value < min_order:
                    continue
                qty[a] += delta_value / prices[a]
                cash -= delta_value * (1 + cost)
            else:
                sell_value = min(-delta_value, qty[a] * prices[a])
                qty[a] -= sell_value / prices[a]
                cash += sell_value * (1 - cost)
                delta_value = -sell_value
            fees_paid += abs(delta_value) * cost
            trades += 1
        equity_curve.append(cash + sum(qty[a] * prices[a] for a in assets))
    return _metrics(equity_curve, series, start, n, bars_per_year, fees_paid, trades, start_cash)


def _metrics(curve, series, start, n, bpy, fees, trades, start_cash) -> dict:
    if len(curve) < 3:
        return {"valid": False}
    r = [math.log(b / a) for a, b in zip(curve, curve[1:]) if a > 0 and b > 0]
    mu = sum(r) / len(r)
    sd = math.sqrt(sum((x - mu) ** 2 for x in r) / max(1, len(r) - 1))
    peak, mdd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    hold = sum(series[a][n - 1] / series[a][start] for a in series) / len(series) - 1
    total = curve[-1] / start_cash - 1
    return {
        "valid": True,
        "bars": len(curve),
        "total_return_pct": round(total * 100, 3),
        "buy_and_hold_pct": round(hold * 100, 3),
        "excess_vs_hold_pct": round((total - hold) * 100, 3),
        "sharpe": round(mu / sd * math.sqrt(bpy), 3) if sd > 0 else 0.0,
        "max_drawdown_pct": round(mdd * 100, 3),
        "trades": trades,
        "fees_paid": round(fees, 4),
        "fees_pct_of_start": round(fees / start_cash * 100, 3),
    }


def fitness(m: dict) -> float:
    """Score à maximiser : rendement ajusté du drawdown, pénalise l'excès de trades."""
    if not m.get("valid"):
        return -1e9
    calmar_like = m["total_return_pct"] / (abs(m["max_drawdown_pct"]) + 5)
    return calmar_like + 0.3 * m["sharpe"] - 0.02 * m["fees_pct_of_start"] * 10
