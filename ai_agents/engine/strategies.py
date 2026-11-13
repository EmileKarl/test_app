"""Stratégies paramétrées : chaque stratégie renvoie une exposition cible 0..1
pour un actif, calculée uniquement avec les prix passés (pas de regard vers le futur).

Les paramètres vivent dans ai_agents/memory/strategies.json (champion) et sont
modifiés par evolve.py, jamais à la main par un agent.
"""

from __future__ import annotations

import math

DEFAULT_PARAMS = {
    "name": "trend_mom_vol_v1",
    "ema_fast": 12,          # en nombre de bougies
    "ema_slow": 48,
    "mom_lookback": 28,
    "vol_lookback": 28,
    "target_vol_annual": 0.6,  # vise ~60 % de vol annualisée par actif
    "w_trend": 0.5,
    "w_mom": 0.5,
    "rebalance_threshold": 0.06,  # écart de poids (fraction du portefeuille) avant d'agir
}

BOUNDS = {
    "ema_fast": (3, 40, int),
    "ema_slow": (20, 200, int),
    "mom_lookback": (5, 120, int),
    "vol_lookback": (10, 120, int),
    "target_vol_annual": (0.2, 1.5, float),
    "w_trend": (0.0, 1.0, float),
    "w_mom": (0.0, 1.0, float),
    "rebalance_threshold": (0.03, 0.25, float),
}


def ema(values: list[float], span: int) -> float:
    k = 2 / (span + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def realized_vol(closes: list[float], lookback: int, bars_per_year: float) -> float:
    w = closes[-(lookback + 1):]
    r = [math.log(b / a) for a, b in zip(w, w[1:])]
    if len(r) < 2:
        return float("inf")
    m = sum(r) / len(r)
    var = sum((x - m) ** 2 for x in r) / (len(r) - 1)
    return math.sqrt(var * bars_per_year)


def min_history(p: dict) -> int:
    return max(p["ema_slow"], p["mom_lookback"], p["vol_lookback"]) + 2


def target_exposure(closes: list[float], p: dict, bars_per_year: float) -> float:
    """Exposition 0..1 : combinaison tendance + momentum, réduite si la vol est élevée."""
    if len(closes) < min_history(p):
        return 0.0
    trend = 1.0 if ema(closes[-p["ema_slow"] * 3:], p["ema_fast"]) > ema(closes[-p["ema_slow"] * 3:], p["ema_slow"]) else 0.0
    mom = 1.0 if closes[-1] > closes[-1 - p["mom_lookback"]] else 0.0
    wsum = p["w_trend"] + p["w_mom"]
    signal = (p["w_trend"] * trend + p["w_mom"] * mom) / wsum if wsum > 0 else 0.0
    vol = realized_vol(closes, p["vol_lookback"], bars_per_year)
    scale = min(1.0, p["target_vol_annual"] / vol) if vol > 0 else 0.0
    return round(signal * scale, 4)


def clamp_params(p: dict) -> dict:
    q = dict(p)
    for k, (lo, hi, typ) in BOUNDS.items():
        q[k] = typ(min(hi, max(lo, q.get(k, DEFAULT_PARAMS[k]))))
    if q["ema_fast"] >= q["ema_slow"]:
        q["ema_fast"] = max(3, q["ema_slow"] // 3)
    return q
