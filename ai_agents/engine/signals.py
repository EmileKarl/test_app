#!/usr/bin/env python3
"""Signaux de marché : techniques, figures de chandeliers, sentiment et dérivés.

Chaque signal renvoie une valeur dans [-1, +1] : +1 = penche à la hausse, -1 = à la baisse.
Le score composite pondère les signaux par les poids APPRIS hors échantillon dans
ai_agents/memory/signal_weights.json (signal_eval.py). Un signal sans pouvoir prédictif
démontré a un poids de 0 : il est affiché mais n'influence rien.

    python3 ai_agents/engine/signals.py report BTC ETH SOL     # rapport lisible + JSON
"""

from __future__ import annotations

import json
import math
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import market  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ROOT / "memory" / "signal_weights.json"
clip = lambda x: max(-1.0, min(1.0, x))  # noqa: E731


# ---------- indicateurs (listes de floats, du plus ancien au plus récent) ----------
def ema_series(v, n):
    k, out = 2 / (n + 1), []
    e = v[0]
    for x in v:
        e = x * k + e * (1 - k)
        out.append(e)
    return out


def rsi(c, n=14):
    g = l = 0.0
    for a, b in zip(c[-n - 1:-1], c[-n:]):
        d = b - a
        g += max(d, 0)
        l += max(-d, 0)
    if g + l == 0:
        return 50.0
    return 100 * g / (g + l)


def stdev(v):
    m = sum(v) / len(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / max(1, len(v) - 1))


# ---------- signaux techniques : f(rows) -> [-1, 1] ----------
def s_rsi(rows):           # RSI brut : >50 haussier, <50 baissier (le signe est appris ensuite)
    return clip((rsi([r["close"] for r in rows]) - 50) / 25)


def s_macd(rows):
    c = [r["close"] for r in rows]
    macd = [a - b for a, b in zip(ema_series(c, 12), ema_series(c, 26))]
    sig = ema_series(macd, 9)
    hist = macd[-1] - sig[-1]
    return clip(hist / (stdev(c[-30:]) * 0.2 + 1e-12))


def s_bollinger(rows):     # %B centré : +1 en haut de bande, -1 en bas
    c = [r["close"] for r in rows][-20:]
    m, sd = sum(c) / len(c), stdev(c)
    return clip((c[-1] - m) / (2 * sd + 1e-12))


def s_ema_trend(rows):     # alignement prix / EMA20 / EMA50 / EMA200
    c = [r["close"] for r in rows]
    e20, e50, e200 = ema_series(c, 20)[-1], ema_series(c, 50)[-1], ema_series(c, min(200, len(c) - 1))[-1]
    return clip(((c[-1] > e20) + (e20 > e50) + (e50 > e200) - 1.5) / 1.5)


def s_momentum(rows, n=14):
    c = [r["close"] for r in rows]
    ret = c[-1] / c[-1 - n] - 1
    vol = stdev([math.log(b / a) for a, b in zip(c[-60:], c[-59:])]) * math.sqrt(n)
    return clip(ret / (2 * vol + 1e-12))


def s_donchian(rows, n=20):  # cassure du plus haut / plus bas sur n périodes
    hi = max(r["high"] for r in rows[-n - 1:-1])
    lo = min(r["low"] for r in rows[-n - 1:-1])
    c = rows[-1]["close"]
    return clip((c - (hi + lo) / 2) / ((hi - lo) / 2 + 1e-12))


def s_volume(rows):        # volume anormal dans le sens de la bougie
    v = [r["volume"] for r in rows[-30:]]
    z = (v[-1] - sum(v[:-1]) / len(v[:-1])) / (stdev(v[:-1]) + 1e-12)
    d = 1 if rows[-1]["close"] >= rows[-1]["open"] else -1
    return clip(d * z / 3)


def s_candles(rows):       # figures : engloutissante, marteau, étoile filante
    p, c = rows[-2], rows[-1]
    body = c["close"] - c["open"]
    rng = c["high"] - c["low"] + 1e-12
    upper = c["high"] - max(c["open"], c["close"])
    lower = min(c["open"], c["close"]) - c["low"]
    score = 0.0
    if body > 0 and p["close"] < p["open"] and c["close"] > p["open"] and c["open"] < p["close"]:
        score += 1      # engloutissante haussière
    if body < 0 and p["close"] > p["open"] and c["close"] < p["open"] and c["open"] > p["close"]:
        score -= 1      # engloutissante baissière
    if lower > 2 * abs(body) and upper < 0.3 * rng:
        score += 0.6    # marteau
    if upper > 2 * abs(body) and lower < 0.3 * rng:
        score -= 0.6    # étoile filante
    return clip(score)


def s_rsi_divergence(rows, look=14):
    c = [r["close"] for r in rows]
    r_now, r_then = rsi(c), rsi(c[:-look])
    p_now, p_then = c[-1], c[-1 - look]
    if p_now < p_then and r_now > r_then:
        return clip((r_now - r_then) / 15)     # divergence haussière
    if p_now > p_then and r_now < r_then:
        return clip(-(r_then - r_now) / 15)    # divergence baissière
    return 0.0


def s_zscore(rows, n=20):  # écart à la moyenne (le signe appris dira si c'est retour ou tendance)
    c = [r["close"] for r in rows][-n:]
    return clip((c[-1] - sum(c) / n) / (2 * stdev(c) + 1e-12))


TECHNICAL = {
    "rsi": s_rsi, "macd": s_macd, "bollinger": s_bollinger, "ema_trend": s_ema_trend,
    "momentum": s_momentum, "donchian": s_donchian, "volume": s_volume,
    "candles": s_candles, "rsi_divergence": s_rsi_divergence, "zscore": s_zscore,
}
MIN_BARS = 210


# ---------- données externes ----------
def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "crypto-desk/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def fear_greed_history(limit=400):
    """[(timestamp, valeur 0-100)] du plus ancien au plus récent (alternative.me)."""
    d = _get(f"https://api.alternative.me/fng/?limit={limit}&format=json")["data"]
    return sorted((int(x["timestamp"]), int(x["value"])) for x in d)


def s_fear_greed(value):   # brut : peur -> négatif ; le poids appris décide si c'est contrarian
    return clip((value - 50) / 40)


def okx_funding(asset):
    """Taux de financement courant du perpétuel OKX (positif = acheteurs paient)."""
    d = _get(f"https://www.okx.com/api/v5/public/funding-rate?instId={asset}-USDT-SWAP")["data"]
    return float(d[0]["fundingRate"]) if d else None


def okx_funding_history(asset, limit=100):
    d = _get(f"https://www.okx.com/api/v5/public/funding-rate-history?instId={asset}-USDT-SWAP&limit={limit}")["data"]
    return sorted((int(x["fundingTime"]) // 1000, float(x["realizedRate"] or x["fundingRate"])) for x in d)


def s_funding(rate):       # brut : financement élevé -> positif
    return clip(rate / 0.0003) if rate is not None else 0.0


# ---------- score ----------
def load_weights():
    try:
        return json.loads(WEIGHTS.read_text())
    except FileNotFoundError:
        return {"weights": {}}


def compute(asset, rows=None, fng=None, funding=None, quote="USDC"):
    """Signaux bruts + score composite pondéré pour un actif (bougies journalières)."""
    rows = rows or market.candles(f"{asset}-{quote}", "ONE_DAY", bars=260)
    raw = {}
    if len(rows) >= MIN_BARS:
        for name, f in TECHNICAL.items():
            raw[name] = round(f(rows), 3)
    if fng is not None:
        raw["fear_greed"] = round(s_fear_greed(fng), 3)
    if funding is not None:
        raw["funding"] = round(s_funding(funding), 3)
    w = load_weights().get("weights", {})
    num = sum(w.get(k, 0.0) * v for k, v in raw.items())
    den = sum(abs(w.get(k, 0.0)) for k in raw) or 0.0
    score = clip(num / den) if den else 0.0
    return {"asset": asset, "signals": raw, "score": round(score, 3),
            "active_signals": [k for k in raw if w.get(k, 0.0) != 0.0]}


def report(assets):
    try:
        fng = fear_greed_history(1)[-1][1]
    except Exception:
        fng = None
    out = {"fear_greed_now": fng, "assets": []}
    for a in assets:
        try:
            fund = okx_funding(a)
        except Exception:
            fund = None
        r = compute(a, fng=fng, funding=fund)
        r["funding_rate"] = fund
        out["assets"].append(r)
    return out


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "report":
        print(json.dumps(report(sys.argv[2:]), indent=2, ensure_ascii=False))
    else:
        raise SystemExit(__doc__)
