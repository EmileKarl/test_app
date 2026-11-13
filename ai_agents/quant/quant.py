#!/usr/bin/env python3
"""Boîte à outils quantitative pour les agents crypto (stdlib uniquement).

Utilisée par les agents `quant-mathematician` et `risk-probabilist` pour que
leurs chiffres viennent d'un calcul réel et non d'une estimation du modèle.

Usage CLI (les prix sont une liste JSON de nombres, du plus ancien au plus récent) :

    echo '[100, 102, 101, 105]' | python3 ai_agents/quant/quant.py stats
    echo '[...]' | python3 ai_agents/quant/quant.py var --confidence 0.95
    echo '[...]' | python3 ai_agents/quant/quant.py montecarlo --days 30 --target 75000 --stop 60000
    python3 ai_agents/quant/quant.py kelly --win-prob 0.55 --win-loss-ratio 1.5
    python3 ai_agents/quant/quant.py size --capital 1000 --risk-pct 1 --entry 68000 --stop 65000

Les prix CoinGecko (`get-coin-market-chart`) peuvent être passés tels quels :
une liste de [timestamp, prix] est aussi acceptée.

Rien ici n'est un conseil financier : ce sont des statistiques descriptives et
des simulations dont les hypothèses (rendements i.i.d., log-normalité) sont
fausses en pratique, surtout en crypto (queues épaisses, ruptures de régime).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from typing import Sequence

# La crypto cote 24/7 : on annualise sur 365 jours, pas 252.
PERIODS_PER_YEAR = 365


def _clean_prices(raw) -> list[float]:
    prices = []
    for item in raw:
        if isinstance(item, (list, tuple)):
            item = item[-1]
        prices.append(float(item))
    if len(prices) < 3:
        raise ValueError("Il faut au moins 3 prix.")
    if any(p <= 0 for p in prices):
        raise ValueError("Les prix doivent être strictement positifs.")
    return prices


def log_returns(prices: Sequence[float]) -> list[float]:
    return [math.log(b / a) for a, b in zip(prices, prices[1:])]


def max_drawdown(prices: Sequence[float]) -> float:
    peak, mdd = prices[0], 0.0
    for p in prices:
        peak = max(peak, p)
        mdd = min(mdd, p / peak - 1)
    return mdd


def stats(prices: Sequence[float], periods_per_year: int = PERIODS_PER_YEAR,
          risk_free: float = 0.0) -> dict:
    r = log_returns(prices)
    mu, sd = statistics.fmean(r), statistics.stdev(r)
    downside = [x for x in r if x < 0]
    dsd = math.sqrt(sum(x * x for x in downside) / len(r)) if downside else 0.0
    ann_mu = mu * periods_per_year
    ann_vol = sd * math.sqrt(periods_per_year)
    n = len(r)
    m3 = sum((x - mu) ** 3 for x in r) / n
    m4 = sum((x - mu) ** 4 for x in r) / n
    var_pop = sum((x - mu) ** 2 for x in r) / n
    return {
        "n_periods": n,
        "total_return_pct": (prices[-1] / prices[0] - 1) * 100,
        "mean_log_return_per_period": mu,
        "vol_per_period": sd,
        "annualized_return_pct": ann_mu * 100,
        "annualized_vol_pct": ann_vol * 100,
        "sharpe": (ann_mu - risk_free) / ann_vol if ann_vol else None,
        "sortino": (ann_mu - risk_free) / (dsd * math.sqrt(periods_per_year)) if dsd else None,
        "max_drawdown_pct": max_drawdown(prices) * 100,
        "skewness": m3 / var_pop ** 1.5 if var_pop else None,
        "excess_kurtosis": m4 / var_pop ** 2 - 3 if var_pop else None,
        "pct_up_periods": sum(1 for x in r if x > 0) / n * 100,
    }


def value_at_risk(prices: Sequence[float], confidence: float = 0.95,
                  horizon: int = 1) -> dict:
    """VaR / CVaR historiques et paramétriques (en % de perte)."""
    r = sorted(log_returns(prices))
    idx = max(0, int(math.floor((1 - confidence) * len(r))) - 1)
    hist_var = r[idx]
    tail = r[: idx + 1]
    hist_cvar = statistics.fmean(tail)
    mu, sd = statistics.fmean(r), statistics.stdev(r)
    z = statistics.NormalDist().inv_cdf(1 - confidence)
    param_var = mu * horizon + z * sd * math.sqrt(horizon)
    scale = math.sqrt(horizon)
    to_pct = lambda lr: (1 - math.exp(lr)) * 100  # noqa: E731
    return {
        "confidence": confidence,
        "horizon_periods": horizon,
        "historical_var_loss_pct": to_pct(hist_var * scale),
        "historical_cvar_loss_pct": to_pct(hist_cvar * scale),
        "parametric_normal_var_loss_pct": to_pct(param_var),
        "note": "La VaR normale sous-estime en général le risque crypto (queues épaisses). "
                "Le passage à l'horizon par racine du temps suppose des rendements i.i.d.",
    }


def monte_carlo(prices: Sequence[float], days: int = 30, n_paths: int = 10_000,
                target: float | None = None, stop: float | None = None,
                seed: int | None = 42, bootstrap: bool = True,
                zero_drift: bool = False) -> dict:
    """Simulation de trajectoires.

    bootstrap=True ré-échantillonne les rendements historiques (garde les queues
    épaisses observées) ; sinon mouvement brownien géométrique.
    Renvoie les quantiles du prix final et, si fournis, la probabilité de
    toucher `target` avant `stop` (et inversement) sur l'horizon.
    zero_drift=True retire la tendance moyenne passée (hypothèse neutre : le
    passé récent ne prédit pas la direction future).
    """
    rng = random.Random(seed)
    r = log_returns(prices)
    mu, sd = statistics.fmean(r), statistics.stdev(r)
    if zero_drift:
        r = [x - mu for x in r]
        mu = 0.0
    s0 = prices[-1]
    finals = []
    hit_target_first = hit_stop_first = 0
    for _ in range(n_paths):
        s, done = s0, False
        for _ in range(days):
            step = rng.choice(r) if bootstrap else rng.gauss(mu, sd)
            s *= math.exp(step)
            if not done and target is not None and s >= target:
                hit_target_first += 1
                done = True
            elif not done and stop is not None and s <= stop:
                hit_stop_first += 1
                done = True
        finals.append(s)
    finals.sort()
    q = lambda p: finals[min(len(finals) - 1, int(p * len(finals)))]  # noqa: E731
    out = {
        "model": ("bootstrap historique" if bootstrap else "GBM normal")
                 + (" sans dérive" if zero_drift else " avec dérive historique"),
        "start_price": s0,
        "days": days,
        "paths": n_paths,
        "final_price_quantiles": {k: q(v) for k, v in
                                  {"p05": .05, "p25": .25, "p50": .5, "p75": .75, "p95": .95}.items()},
        "prob_final_above_start": sum(1 for f in finals if f > s0) / n_paths,
    }
    if target is not None:
        out["prob_hit_target_first"] = hit_target_first / n_paths
    if stop is not None:
        out["prob_hit_stop_first"] = hit_stop_first / n_paths
    if target is not None or stop is not None:
        out["prob_neither"] = 1 - (hit_target_first + hit_stop_first) / n_paths
    return out


def kelly(win_prob: float, win_loss_ratio: float, fraction: float = 0.25) -> dict:
    """Critère de Kelly f* = p - (1-p)/b, avec Kelly fractionnaire recommandé."""
    if not 0 < win_prob < 1 or win_loss_ratio <= 0:
        raise ValueError("win_prob dans ]0,1[ et win_loss_ratio > 0.")
    f = win_prob - (1 - win_prob) / win_loss_ratio
    ev = win_prob * win_loss_ratio - (1 - win_prob)
    return {
        "full_kelly_pct": f * 100,
        f"fractional_kelly_{fraction}_pct": max(0.0, f * fraction) * 100,
        "expected_value_per_unit_risked": ev,
        "edge": "positive" if f > 0 else "aucun avantage: ne pas parier",
        "note": "Kelly suppose des probabilités connues ; elles sont estimées, "
                "donc on utilise une fraction (1/4) de Kelly.",
    }


def position_size(capital: float, risk_pct: float, entry: float, stop: float,
                  fee_pct: float = 0.6) -> dict:
    """Taille de position pour ne risquer que `risk_pct` % du capital jusqu'au stop.

    fee_pct : frais aller-retour estimés en % (ordre taker Coinbase Advanced
    ≈ 0,6 % par côté sur les petits volumes ; à vérifier sur votre palier).
    """
    risk_amount = capital * risk_pct / 100
    per_unit_loss = abs(entry - stop) + entry * fee_pct / 100 * 2
    qty = risk_amount / per_unit_loss
    notional = qty * entry
    return {
        "risk_amount": risk_amount,
        "quantity": qty,
        "notional": notional,
        "notional_pct_of_capital": notional / capital * 100,
        "capped": notional > capital,
        "note": "Si 'capped' est vrai, la position dépasse le capital : réduire ou élargir le stop.",
    }


def correlation(a: Sequence[float], b: Sequence[float]) -> float:
    ra, rb = log_returns(a), log_returns(b)
    n = min(len(ra), len(rb))
    return statistics.correlation(ra[-n:], rb[-n:])


def _read_stdin_prices():
    """Accepte une liste de prix, ou l'objet JSON complet de CoinGecko
    `get-coin-market-chart` ({"prices": [...], "startTs": ..., "endTs": ...}).
    Renvoie (prix, durée d'une période en jours)."""
    data = json.load(sys.stdin)
    period_days = 1.0
    if isinstance(data, dict):
        prices = _clean_prices(data["prices"])
        if "startTs" in data and "endTs" in data:
            span_days = (data["endTs"] - data["startTs"]) / 86_400_000
            period_days = span_days / (len(prices) - 1)
    else:
        prices = _clean_prices(data)
    return prices, period_days


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats")
    v = sub.add_parser("var")
    v.add_argument("--confidence", type=float, default=0.95)
    v.add_argument("--horizon", type=int, default=1, help="horizon en jours")
    m = sub.add_parser("montecarlo")
    m.add_argument("--days", type=int, default=30)
    m.add_argument("--paths", type=int, default=10_000)
    m.add_argument("--target", type=float)
    m.add_argument("--stop", type=float)
    m.add_argument("--gbm", action="store_true", help="GBM normal au lieu du bootstrap")
    m.add_argument("--seed", type=int, default=42)
    m.add_argument("--zero-drift", action="store_true", help="Retirer la tendance historique (recommandé)")
    k = sub.add_parser("kelly")
    k.add_argument("--win-prob", type=float, required=True)
    k.add_argument("--win-loss-ratio", type=float, required=True)
    k.add_argument("--fraction", type=float, default=0.25)
    s = sub.add_parser("size")
    s.add_argument("--capital", type=float, required=True)
    s.add_argument("--risk-pct", type=float, required=True)
    s.add_argument("--entry", type=float, required=True)
    s.add_argument("--stop", type=float, required=True)
    s.add_argument("--fee-pct", type=float, default=0.6)
    c = sub.add_parser("corr", help='stdin: {"a": [...], "b": [...]}')
    for sp in (sub.choices["stats"], v, m):
        sp.add_argument("--period-days", type=float,
                        help="Durée d'un pas en jours (déduite auto. du JSON CoinGecko, sinon 1)")
    args = p.parse_args(argv)

    if args.cmd in ("stats", "var", "montecarlo"):
        prices, period_days = _read_stdin_prices()
        if args.period_days:
            period_days = args.period_days
    if args.cmd == "stats":
        out = stats(prices, periods_per_year=round(PERIODS_PER_YEAR / period_days))
        out["period_days"] = period_days
    elif args.cmd == "var":
        # horizon exprimé en jours -> converti en nombre de pas
        steps = max(1, round(args.horizon / period_days))
        out = value_at_risk(prices, args.confidence, steps)
        out["horizon_days"] = args.horizon
    elif args.cmd == "montecarlo":
        steps = max(1, round(args.days / period_days))
        out = monte_carlo(prices, steps, args.paths, args.target,
                          args.stop, args.seed, bootstrap=not args.gbm,
                          zero_drift=args.zero_drift)
        out["days"] = args.days
        out["steps"] = steps
    elif args.cmd == "kelly":
        out = kelly(args.win_prob, args.win_loss_ratio, args.fraction)
    elif args.cmd == "size":
        out = position_size(args.capital, args.risk_pct, args.entry, args.stop, args.fee_pct)
    elif args.cmd == "corr":
        d = json.load(sys.stdin)
        out = {"correlation_log_returns": correlation(_clean_prices(d["a"]), _clean_prices(d["b"]))}
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
